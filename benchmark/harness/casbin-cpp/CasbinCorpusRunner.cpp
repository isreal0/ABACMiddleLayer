// Correctness-only runner for the Casbin-CPP adapter (Step 4/5A). Reads the
// same scenarios.tsv format used by the Middle Layer adapter, evaluates each
// scenario through casbin::Enforcer against model.conf/policy.csv (the
// single-matcher translation of the shared reference policy), and writes one
// normalized JSON line per scenario matching benchmark/schemas/result.schema.json.
//
// Casbin has no NotApplicable/Indeterminate concept -- Enforce() is strictly
// boolean -- so any scenario whose canonical `expected` is "NotApplicable"
// is marked supported=false, correct=null, rather than forced into a
// misleading Permit/Deny comparison. See benchmark/docs/semantic-mapping.md.
//
// Usage: casbin_corpus_runner <modelConf> <policyCsv> <scenariosTsv> <outputJsonl> <corpusCommit> <adapterCommit>

#include "casbin/enforcer.h"

#include <nlohmann/json.hpp>

#include <chrono>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <string>
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

int main(int argc, char** argv) {
    if (argc != 7) {
        std::cerr << "usage: casbin_corpus_runner <modelConf> <policyCsv> <scenariosTsv> "
                     "<outputJsonl> <corpusCommit> <adapterCommit>\n";
        return 2;
    }
    std::string modelConf = argv[1];
    std::string policyCsv = argv[2];
    std::string scenariosTsv = argv[3];
    std::string outputJsonl = argv[4];
    std::string corpusCommit = argv[5];
    std::string adapterCommit = argv[6];

    // Enforcer's constructor is what parses model.conf and every row of
    // policy.csv, so this is genuinely the policy-load cost, not just
    // object construction.
    auto loadStart = std::chrono::steady_clock::now();
    casbin::Enforcer enforcer(modelConf, policyCsv);
    long long policyLoadNs = std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now() - loadStart).count();

    char hostname[256] = {0};
    gethostname(hostname, sizeof(hostname));

    auto now = std::chrono::system_clock::now().time_since_epoch();
    long long runIdMs = std::chrono::duration_cast<std::chrono::milliseconds>(now).count();
    std::string runId = "run-" + std::to_string(runIdMs);

    std::ifstream in(scenariosTsv);
    std::string line;
    std::getline(in, line);  // header
    std::vector<std::string> header = splitTab(line);

    std::ofstream out(outputJsonl);
    int total = 0, correct = 0, supportedCount = 0;

    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::vector<std::string> row = splitTab(line);
        std::map<std::string, std::string> f;
        for (size_t i = 0; i < header.size() && i < row.size(); i++) {
            f[header[i]] = row[i];
        }
        total++;

        json subJ = {{"id", f["subject_id"]}};
        if (!f["subject_role"].empty()) subJ["role"] = f["subject_role"];
        if (!f["subject_department"].empty()) subJ["department"] = f["subject_department"];
        if (!f["subject_clearance"].empty()) subJ["clearance"] = std::stoi(f["subject_clearance"]);

        json objJ = {{"id", f["resource_id"]}};
        if (!f["resource_owner"].empty()) objJ["owner"] = f["resource_owner"];
        if (!f["resource_department"].empty()) objJ["department"] = f["resource_department"];
        if (!f["resource_classification"].empty()) objJ["classification"] = std::stoi(f["resource_classification"]);

        json envJ = json::object();
        if (!f["env_network"].empty()) envJ["network"] = f["env_network"];
        if (!f["env_hour"].empty()) envJ["hour"] = std::stoi(f["env_hour"]);

        auto subPtr = std::make_shared<json>(subJ);
        auto objPtr = std::make_shared<json>(objJ);
        auto envPtr = std::make_shared<json>(envJ);

        casbin::DataMap params = {
            {"sub", subPtr}, {"obj", objPtr}, {"act", f["action"]}, {"env", envPtr},
        };

        std::string expected = f["expected"];
        std::string actual;
        std::string error;
        bool supported = (expected != "NotApplicable");

        auto evalStart = std::chrono::steady_clock::now();
        try {
            bool result = enforcer.Enforce(params);
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
