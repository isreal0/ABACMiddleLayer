// Runner for the Casbin-CPP adapter, two modes:
//
// Correctness (Step 4/5A):
//   casbin_corpus_runner <modelConf> <policyCsv> <scenariosTsv> <outputJsonl> <corpusCommit> <adapterCommit>
//
// Benchmark (Step 5B):
//   casbin_corpus_runner benchmark <modelConf> <policyCsv> <scenariosTsv> <manifestConf> <rawOutputTsv> <summaryOutputJson>
//
// Casbin has no NotApplicable/Indeterminate concept -- Enforce() is strictly
// boolean -- so any scenario whose canonical `expected` is "NotApplicable"
// is marked supported=false, correct=null, rather than forced into a
// misleading Permit/Deny comparison. See benchmark/docs/semantic-mapping.md.

#include "casbin/enforcer.h"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>
#include <unistd.h>

using json = nlohmann::json;

static std::vector<std::string> splitTab(const std::string& line) {
    std::vector<std::string> out;
    size_t start = 0;
    while (true) {
        size_t pos = line.find('\t', start);
        if (pos == std::string::npos) {
            out.push_back(line.substr(start));
            break;
        }
        out.push_back(line.substr(start, pos - start));
        start = pos + 1;
    }
    return out;
}

static std::string jsonEscape(const std::string& s) {
    std::string out;
    for (char c : s) {
        if (c == '"' || c == '\\') out.push_back('\\');
        out.push_back(c);
    }
    return out;
}

static std::string getHostname() {
    char hostname[256] = {0};
    gethostname(hostname, sizeof(hostname));
    return std::string(hostname);
}

static std::vector<std::vector<std::string>> readTsvRows(const std::string& path) {
    std::vector<std::vector<std::string>> rows;
    std::ifstream in(path);
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        rows.push_back(splitTab(line));
    }
    return rows;
}

static std::map<std::string, std::string> readManifestConf(const std::string& path) {
    std::map<std::string, std::string> m;
    std::ifstream in(path);
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') continue;
        size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        m[line.substr(0, eq)] = line.substr(eq + 1);
    }
    return m;
}

static casbin::DataMap buildDataMap(const std::map<std::string, std::string>& f) {
    json subJ = {{"id", f.at("subject_id")}};
    if (!f.at("subject_role").empty()) subJ["role"] = f.at("subject_role");
    if (!f.at("subject_department").empty()) subJ["department"] = f.at("subject_department");
    if (!f.at("subject_clearance").empty()) subJ["clearance"] = std::stoi(f.at("subject_clearance"));

    json objJ = {{"id", f.at("resource_id")}};
    if (!f.at("resource_owner").empty()) objJ["owner"] = f.at("resource_owner");
    if (!f.at("resource_department").empty()) objJ["department"] = f.at("resource_department");
    if (!f.at("resource_classification").empty()) objJ["classification"] = std::stoi(f.at("resource_classification"));

    json envJ = json::object();
    if (!f.at("env_network").empty()) envJ["network"] = f.at("env_network");
    if (!f.at("env_hour").empty()) envJ["hour"] = std::stoi(f.at("env_hour"));

    auto subPtr = std::make_shared<json>(subJ);
    auto objPtr = std::make_shared<json>(objJ);
    auto envPtr = std::make_shared<json>(envJ);

    return casbin::DataMap{
        {"sub", subPtr}, {"obj", objPtr}, {"act", f.at("action")}, {"env", envPtr},
    };
}

static long readPeakRssKb() {
    std::ifstream in("/proc/self/status");
    std::string line;
    while (std::getline(in, line)) {
        if (line.rfind("VmHWM:", 0) == 0) {
            std::istringstream iss(line.substr(6));
            long kb;
            iss >> kb;
            return kb;
        }
    }
    return -1;
}

static long long percentileNs(std::vector<long long>& sorted, double p) {
    long idx = static_cast<long>(std::ceil(p * sorted.size())) - 1;
    if (idx < 0) idx = 0;
    if (idx >= static_cast<long>(sorted.size())) idx = sorted.size() - 1;
    return sorted[idx];
}

static void writeSummary(const std::string& path, const std::string& engine, std::vector<long long> latenciesNs,
                          int warmup, int measured, int repetitions, int concurrency, double aggregateThroughput) {
    std::sort(latenciesNs.begin(), latenciesNs.end());
    size_t n = latenciesNs.size();
    double sum = 0;
    for (auto v : latenciesNs) sum += static_cast<double>(v);
    double mean = sum / n;
    double variance = 0;
    for (auto v : latenciesNs) {
        double d = static_cast<double>(v) - mean;
        variance += d * d;
    }
    double stddev = std::sqrt(variance / n);
    long long minV = latenciesNs.front();
    long long maxV = latenciesNs.back();
    long long median = percentileNs(latenciesNs, 0.50);
    long long p95 = percentileNs(latenciesNs, 0.95);
    long long p99 = percentileNs(latenciesNs, 0.99);
    long peakRss = readPeakRssKb();

    std::ofstream out(path);
    out << "{\n"
        << "  \"engine\": \"" << engine << "\",\n"
        << "  \"concurrency\": " << concurrency << ",\n"
        << "  \"warmup_iterations\": " << warmup << ",\n"
        << "  \"measured_iterations_per_worker\": " << measured << ",\n"
        << "  \"repetitions\": " << repetitions << ",\n"
        << "  \"sample_count\": " << n << ",\n"
        << "  \"latency_ns\": {\n"
        << "    \"min\": " << minV << ",\n"
        << "    \"median\": " << median << ",\n"
        << "    \"mean\": " << static_cast<long long>(std::round(mean)) << ",\n"
        << "    \"p95\": " << p95 << ",\n"
        << "    \"p99\": " << p99 << ",\n"
        << "    \"max\": " << maxV << ",\n"
        << "    \"stddev\": " << static_cast<long long>(std::round(stddev)) << "\n"
        << "  },\n"
        << "  \"aggregate_throughput_per_sec\": " << aggregateThroughput << ",\n"
        << "  \"peak_rss_kb\": " << peakRss << "\n"
        << "}\n";
}

static int runCorrectness(const std::string& modelConf, const std::string& policyCsv, const std::string& scenariosTsv,
                           const std::string& outputJsonl, const std::string& corpusCommit, const std::string& adapterCommit) {
    auto loadStart = std::chrono::steady_clock::now();
    casbin::Enforcer enforcer(modelConf, policyCsv);
    long long policyLoadNs = std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now() - loadStart).count();

    std::string hostname = getHostname();
    auto now = std::chrono::system_clock::now().time_since_epoch();
    long long runIdMs = std::chrono::duration_cast<std::chrono::milliseconds>(now).count();
    std::string runId = "run-" + std::to_string(runIdMs);

    auto rows = readTsvRows(scenariosTsv);
    std::vector<std::string> header = rows.front();

    std::ofstream out(outputJsonl);
    int total = 0, correct = 0, supportedCount = 0;

    for (size_t r = 1; r < rows.size(); r++) {
        std::map<std::string, std::string> f;
        for (size_t i = 0; i < header.size() && i < rows[r].size(); i++) f[header[i]] = rows[r][i];
        total++;

        std::string expected = f["expected"];
        std::string actual, error;
        bool supported = (expected != "NotApplicable");

        auto evalStart = std::chrono::steady_clock::now();
        try {
            bool result = enforcer.Enforce(buildDataMap(f));
            actual = result ? "Permit" : "Deny";
        } catch (const std::exception& e) {
            actual = "";
            error = e.what();
            supported = false;
        }
        long long evalNs = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now() - evalStart).count();

        bool isCorrect = supported && (actual == expected);
        if (supported) {
            supportedCount++;
            if (isCorrect) correct++;
        }

        out << "{"
            << "\"run_id\":\"" << runId << "\","
            << "\"engine\":\"casbin-cpp\","
            << "\"engine_version\":\"ce8c55ed1\","
            << "\"hostname\":\"" << jsonEscape(hostname) << "\","
            << "\"corpus_commit\":\"" << corpusCommit << "\","
            << "\"adapter_commit\":\"" << adapterCommit << "\","
            << "\"scenario_id\":\"" << f["id"] << "\","
            << "\"expected\":\"" << expected << "\","
            << "\"actual\":" << (actual.empty() ? "null" : ("\"" + jsonEscape(actual) + "\"")) << ","
            << "\"supported\":" << (supported ? "true" : "false") << ","
            << "\"correct\":" << (supported ? (isCorrect ? "true" : "false") : "null") << ","
            << "\"policy_load_ns\":" << policyLoadNs << ",\"translation_ns\":null,"
            << "\"evaluation_ns\":" << evalNs << ",\"total_ns\":" << evalNs << ","
            << "\"error\":" << (error.empty() ? "null" : ("\"" + jsonEscape(error) + "\"")) << ","
            << "\"notes\":" << (supported ? "null" : "\"Casbin has no NotApplicable/Indeterminate concept; Enforce() is strictly boolean\"")
            << "}\n";
    }

    std::cout << "Casbin-CPP correctness: " << correct << "/" << supportedCount
              << " supported scenarios correct (" << (total - supportedCount)
              << " of " << total << " marked unsupported: no NotApplicable concept)\n";
    return (correct == supportedCount) ? 0 : 1;
}

struct WorkerResult {
    std::vector<long long> latencies;
    std::vector<std::string> rawLines;
};

static void benchmarkWorker(casbin::Enforcer* enforcer, const std::vector<std::map<std::string, std::string>>* scenarios,
                             int workerId, int measured, WorkerResult* result) {
    size_t n = scenarios->size();
    for (int i = 0; i < measured; i++) {
        const auto& sc = (*scenarios)[i % n];
        auto start = std::chrono::steady_clock::now();
        try { enforcer->Enforce(buildDataMap(sc)); } catch (...) {}
        long long latencyNs = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now() - start).count();
        result->latencies.push_back(latencyNs);
        result->rawLines.push_back(std::to_string(workerId) + "\t" + std::to_string(i) + "\t" + sc.at("id") + "\t" + std::to_string(latencyNs));
    }
}

static int runBenchmark(const std::string& modelConf, const std::string& policyCsv, const std::string& scenariosTsv,
                         const std::string& manifestConf, int concurrency,
                         const std::string& rawOutputTsv, const std::string& summaryOutputJson) {
    auto manifest = readManifestConf(manifestConf);
    int warmup = std::stoi(manifest["warmup_iterations"]);
    int measured = std::stoi(manifest["measured_iterations"]);
    int repetitions = std::stoi(manifest["repetitions"]);

    auto rows = readTsvRows(scenariosTsv);
    std::vector<std::string> header = rows.front();
    std::vector<std::map<std::string, std::string>> scenarios;
    for (size_t r = 1; r < rows.size(); r++) {
        std::map<std::string, std::string> f;
        for (size_t i = 0; i < header.size() && i < rows[r].size(); i++) f[header[i]] = rows[r][i];
        scenarios.push_back(f);
    }
    size_t n = scenarios.size();

    // casbin::Enforcer::Enforce() is NOT thread-safe for concurrent calls on
    // a single shared instance -- confirmed empirically (segfaults at
    // concurrency >= 2 with one shared instance). Each worker therefore
    // gets its OWN independently-loaded Enforcer instance rather than
    // sharing one; this measures N independent Casbin instances serving
    // requests concurrently (e.g. N replicas behind a load balancer), not
    // "one instance handling concurrent requests", which this library does
    // not support without external locking. See docs/semantic-mapping.md.
    std::vector<std::unique_ptr<casbin::Enforcer>> enforcers;
    for (int w = 0; w < concurrency; w++) {
        enforcers.push_back(std::unique_ptr<casbin::Enforcer>(new casbin::Enforcer(modelConf, policyCsv)));
    }

    for (int i = 0; i < warmup; i++) {
        try { enforcers[0]->Enforce(buildDataMap(scenarios[i % n])); } catch (...) {}
    }

    std::vector<long long> allLatencies;
    std::vector<std::string> allRawLines;
    double totalWallSeconds = 0;

    for (int rep = 0; rep < repetitions; rep++) {
        std::vector<WorkerResult> results(concurrency);
        std::vector<std::thread> threads;
        auto repStart = std::chrono::steady_clock::now();
        for (int w = 0; w < concurrency; w++) {
            threads.emplace_back(benchmarkWorker, enforcers[w].get(), &scenarios, w, measured, &results[w]);
        }
        for (auto& t : threads) t.join();
        totalWallSeconds += std::chrono::duration_cast<std::chrono::duration<double>>(
            std::chrono::steady_clock::now() - repStart).count();
        for (auto& r : results) {
            allLatencies.insert(allLatencies.end(), r.latencies.begin(), r.latencies.end());
            allRawLines.insert(allRawLines.end(), r.rawLines.begin(), r.rawLines.end());
        }
    }

    std::ofstream rawOut(rawOutputTsv);
    rawOut << "worker\titeration\tscenario_id\tlatency_ns\n";
    for (const auto& line : allRawLines) rawOut << line << "\n";
    rawOut.close();

    double aggregateThroughput = static_cast<double>(allLatencies.size()) / totalWallSeconds;
    writeSummary(summaryOutputJson, "casbin-cpp", allLatencies, warmup, measured, repetitions, concurrency, aggregateThroughput);
    std::cout << "Casbin-CPP benchmark (concurrency=" << concurrency << "): " << allLatencies.size()
              << " measured calls, aggregate throughput " << aggregateThroughput << "/s, summary written to " << summaryOutputJson << "\n";
    return 0;
}

// Single-process, single-threaded worker used by scripts/run-casbin-benchmark.py
// for concurrency testing: casbin::Enforcer is not safe for concurrent use
// from multiple threads even with one instance per thread (confirmed
// empirically -- segfaults at concurrency >= 2 either way, pointing at
// global/static state inside the library, likely the vendored Exprtk
// expression engine, not just per-instance state). Concurrency is instead
// achieved the same way as AuthzForce: independent OS processes, no shared
// memory at all. Writes only latency_ns per iteration (no repetitions
// concept here -- the Python orchestrator calls this once per repetition).
//
// Usage: casbin_corpus_runner benchmark-worker <modelConf> <policyCsv> <scenariosTsv> <measured> <rawOutputTsv>
static int runBenchmarkWorker(const std::string& modelConf, const std::string& policyCsv, const std::string& scenariosTsv,
                               int measured, const std::string& rawOutputTsv) {
    casbin::Enforcer enforcer(modelConf, policyCsv);

    auto rows = readTsvRows(scenariosTsv);
    std::vector<std::string> header = rows.front();
    std::vector<std::map<std::string, std::string>> scenarios;
    for (size_t r = 1; r < rows.size(); r++) {
        std::map<std::string, std::string> f;
        for (size_t i = 0; i < header.size() && i < rows[r].size(); i++) f[header[i]] = rows[r][i];
        scenarios.push_back(f);
    }
    size_t n = scenarios.size();

    std::ofstream rawOut(rawOutputTsv);
    rawOut << "iteration\tscenario_id\tlatency_ns\n";
    for (int i = 0; i < measured; i++) {
        const auto& sc = scenarios[i % n];
        auto start = std::chrono::steady_clock::now();
        try { enforcer.Enforce(buildDataMap(sc)); } catch (...) {}
        long long latencyNs = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now() - start).count();
        rawOut << i << "\t" << sc.at("id") << "\t" << latencyNs << "\n";
    }
    return 0;
}

int main(int argc, char** argv) {
    if (argc == 7 && std::string(argv[1]) == "benchmark-worker") {
        return runBenchmarkWorker(argv[2], argv[3], argv[4], std::stoi(argv[5]), argv[6]);
    }
    if (argc == 9 && std::string(argv[1]) == "benchmark") {
        return runBenchmark(argv[2], argv[3], argv[4], argv[5], std::stoi(argv[6]), argv[7], argv[8]);
    }
    if (argc != 7) {
        std::cerr << "usage: casbin_corpus_runner <modelConf> <policyCsv> <scenariosTsv> "
                     "<outputJsonl> <corpusCommit> <adapterCommit>\n"
                  << "   or: casbin_corpus_runner benchmark <modelConf> <policyCsv> <scenariosTsv> "
                     "<manifestConf> <concurrency> <rawOutputTsv> <summaryOutputJson>\n";
        return 2;
    }
    return runCorrectness(argv[1], argv[2], argv[3], argv[4], argv[5], argv[6]);
}
