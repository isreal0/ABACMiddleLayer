import com.sun.xacml.PDP;
import com.sun.xacml.PDPConfig;
import com.sun.xacml.ctx.RequestCtx;
import com.sun.xacml.ctx.ResponseCtx;
import com.sun.xacml.ctx.Result;
import com.sun.xacml.finder.AttributeFinder;
import com.sun.xacml.finder.PolicyFinder;
import com.sun.xacml.finder.PolicyFinderModule;
import com.sun.xacml.finder.ResourceFinder;
import com.sun.xacml.support.finder.FilePolicyModule;

import java.io.BufferedReader;
import java.io.FileInputStream;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/**
 * Runner for the SunXACML adapter, two modes:
 *
 * Correctness (Step 4/5A):
 *   SunXacmlCorpusRunner <policyXml> <requestsDir> <manifestTsv> <outputJsonl> <corpusCommit> <adapterCommit>
 *
 * Benchmark (Step 5B):
 *   SunXacmlCorpusRunner benchmark <policyXml> <requestsDir> <manifestConf> <rawOutputTsv> <summaryOutputJson>
 *
 * Standalone (not a Maven project) -- compile with:
 *   javac -cp "sunxacml-2.0-M1.jar:jaxb-libs/*" SunXacmlCorpusRunner.java
 * Run with the same classpath plus the compiled class directory.
 */
public class SunXacmlCorpusRunner {

    public static void main(String[] args) throws Exception {
        if (args.length == 7 && "benchmark".equals(args[0])) {
            runBenchmark(args[1], args[2], args[3], args[4], args[5], args[6]);
            return;
        }
        if (args.length != 6) {
            System.err.println("usage: SunXacmlCorpusRunner <policyXml> <requestsDir> <manifestTsv> <outputJsonl> <corpusCommit> <adapterCommit>");
            System.err.println("   or: SunXacmlCorpusRunner benchmark <policyXml> <requestsDir> <manifestConf> <concurrency> <rawOutputTsv> <summaryOutputJson>");
            System.exit(2);
        }
        runCorrectness(args[0], args[1], args[2], args[3], args[4], args[5]);
    }

    private static final class WorkerResult {
        final List<Long> latencies = new ArrayList<Long>();
        final List<String> rawLines = new ArrayList<String>();
    }

    private static PDP buildPdp(String policyXml, long[] policyLoadNsOut) {
        List<String> policyFiles = new ArrayList<String>();
        policyFiles.add(policyXml);
        FilePolicyModule filePolicyModule = new FilePolicyModule(policyFiles);

        PolicyFinder policyFinder = new PolicyFinder();
        Set<PolicyFinderModule> modules = new HashSet<PolicyFinderModule>();
        modules.add(filePolicyModule);
        policyFinder.setModules(modules);

        AttributeFinder attributeFinder = new AttributeFinder();
        attributeFinder.setModules(new ArrayList());
        ResourceFinder resourceFinder = new ResourceFinder();

        PDPConfig pdpConfig = new PDPConfig(attributeFinder, policyFinder, resourceFinder);
        // PDP's constructor is what actually triggers PolicyFinder.init(),
        // which is where FilePolicyModule parses every rule in policy.xml --
        // so this is genuinely the policy-load cost, not just object setup.
        long loadStart = System.nanoTime();
        PDP pdp = new PDP(pdpConfig);
        policyLoadNsOut[0] = System.nanoTime() - loadStart;
        return pdp;
    }

    private static String evaluateRequestFile(PDP pdp, String requestPath) throws Exception {
        FileInputStream fis = new FileInputStream(requestPath);
        try {
            RequestCtx requestCtx = RequestCtx.getInstance(fis);
            ResponseCtx responseCtx = pdp.evaluate(requestCtx);
            Result result = (Result) responseCtx.getResults().iterator().next();
            return decisionToString(result.getDecision());
        } finally {
            fis.close();
        }
    }

    private static void runCorrectness(String policyXml, String requestsDir, String manifestTsv, String outputJsonl,
                                        String corpusCommit, String adapterCommit) throws Exception {
        long[] policyLoadNsOut = new long[1];
        PDP pdp = buildPdp(policyXml, policyLoadNsOut);
        long policyLoadNs = policyLoadNsOut[0];

        String hostname = java.net.InetAddress.getLocalHost().getHostName();
        String runId = "run-" + System.currentTimeMillis();

        List<String[]> manifest = readTsv(manifestTsv);
        int total = 0;
        int correct = 0;

        PrintWriter out = new PrintWriter(new FileWriter(outputJsonl));
        try {
            for (int i = 1; i < manifest.size(); i++) {
                String id = manifest.get(i)[0];
                String expected = manifest.get(i)[1];
                total++;

                String actual = null;
                String error = null;
                long evalStart = System.nanoTime();
                try {
                    actual = evaluateRequestFile(pdp, requestsDir + "/" + id + ".xml");
                } catch (Exception e) {
                    error = e.toString();
                }
                long evalNs = System.nanoTime() - evalStart;

                boolean isCorrect = actual != null && actual.equals(expected);
                if (isCorrect) {
                    correct++;
                }
                out.println(toJsonLine(runId, hostname, corpusCommit, adapterCommit, id, expected, actual, isCorrect, error,
                        policyLoadNs, evalNs));
            }
        } finally {
            out.close();
        }

        System.out.println("SunXACML correctness: " + correct + "/" + total + " scenarios correct");
        System.exit(correct == total ? 0 : 1);
    }

    private static void runBenchmark(String policyXml, String requestsDir, String manifestConf,
                                      String concurrencyStr, String rawOutputTsv, String summaryOutputJson) throws Exception {
        long[] policyLoadNsOut = new long[1];
        final PDP pdp = buildPdp(policyXml, policyLoadNsOut);
        final int concurrency = Integer.parseInt(concurrencyStr);

        Map<String, String> manifest = readManifest(manifestConf);
        final int warmup = Integer.parseInt(manifest.get("warmup_iterations"));
        final int measured = Integer.parseInt(manifest.get("measured_iterations"));
        final int repetitions = Integer.parseInt(manifest.get("repetitions"));

        // scenario ids come from the request file names already generated for correctness
        List<String[]> requestManifest = readTsv(requestsDir.replace("/requests", "/manifest.tsv"));
        final List<String> scenarioIds = new ArrayList<String>();
        for (int i = 1; i < requestManifest.size(); i++) {
            scenarioIds.add(requestManifest.get(i)[0]);
        }
        final int n = scenarioIds.size();
        final String reqDir = requestsDir;

        for (int i = 0; i < warmup; i++) {
            try {
                evaluateRequestFile(pdp, requestsDir + "/" + scenarioIds.get(i % n) + ".xml");
            } catch (Exception e) {
                // ignored during warm-up
            }
        }

        ExecutorService pool = Executors.newFixedThreadPool(concurrency);
        List<Long> allLatencies = new ArrayList<Long>();
        List<String> allRawLines = new ArrayList<String>();
        double totalWallSeconds = 0;

        try {
            for (int rep = 0; rep < repetitions; rep++) {
                List<Callable<WorkerResult>> tasks = new ArrayList<Callable<WorkerResult>>();
                for (int w = 0; w < concurrency; w++) {
                    final int workerId = w;
                    tasks.add(new Callable<WorkerResult>() {
                        public WorkerResult call() {
                            WorkerResult r = new WorkerResult();
                            for (int i = 0; i < measured; i++) {
                                String sid = scenarioIds.get(i % n);
                                long start = System.nanoTime();
                                try {
                                    evaluateRequestFile(pdp, reqDir + "/" + sid + ".xml");
                                } catch (Exception e) {
                                    // still record latency of the failed call
                                }
                                long latencyNs = System.nanoTime() - start;
                                r.latencies.add(Long.valueOf(latencyNs));
                                r.rawLines.add(workerId + "\t" + i + "\t" + sid + "\t" + latencyNs);
                            }
                            return r;
                        }
                    });
                }
                long repStart = System.nanoTime();
                List<Future<WorkerResult>> futures = pool.invokeAll(tasks);
                totalWallSeconds += (System.nanoTime() - repStart) / 1e9;
                for (Future<WorkerResult> f : futures) {
                    WorkerResult r = f.get();
                    allLatencies.addAll(r.latencies);
                    allRawLines.addAll(r.rawLines);
                }
            }
        } finally {
            pool.shutdown();
        }

        PrintWriter rawOut = new PrintWriter(new FileWriter(rawOutputTsv));
        try {
            rawOut.println("worker\titeration\tscenario_id\tlatency_ns");
            for (String line : allRawLines) {
                rawOut.println(line);
            }
        } finally {
            rawOut.close();
        }

        double aggregateThroughput = allLatencies.size() / totalWallSeconds;
        writeSummary(summaryOutputJson, "sunxacml", allLatencies, warmup, measured, repetitions, concurrency, aggregateThroughput);
        System.out.println("SunXACML benchmark (concurrency=" + concurrency + "): " + allLatencies.size()
                + " measured calls, aggregate throughput " + aggregateThroughput + "/s, summary written to " + summaryOutputJson);
    }

    private static String decisionToString(int decision) {
        switch (decision) {
            case Result.DECISION_PERMIT: return "Permit";
            case Result.DECISION_DENY: return "Deny";
            case Result.DECISION_NOT_APPLICABLE: return "NotApplicable";
            default: return "Indeterminate";
        }
    }

    private static Map<String, String> readManifest(String path) throws Exception {
        Map<String, String> m = new HashMap<String, String>();
        BufferedReader br = new BufferedReader(new FileReader(path));
        try {
            String line;
            while ((line = br.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty() || line.startsWith("#")) continue;
                int eq = line.indexOf('=');
                if (eq < 0) continue;
                m.put(line.substring(0, eq).trim(), line.substring(eq + 1).trim());
            }
        } finally {
            br.close();
        }
        return m;
    }

    private static long readPeakRssKb() {
        try {
            BufferedReader br = new BufferedReader(new FileReader("/proc/self/status"));
            try {
                String line;
                while ((line = br.readLine()) != null) {
                    if (line.startsWith("VmHWM:")) {
                        return Long.parseLong(line.trim().split("\\s+")[1]);
                    }
                }
            } finally {
                br.close();
            }
        } catch (Exception e) {
            // not on Linux, or /proc unavailable
        }
        return -1;
    }

    private static void writeSummary(String path, String engine, List<Long> latenciesNs,
                                      int warmup, int measured, int repetitions,
                                      int concurrency, double aggregateThroughputPerSec) throws Exception {
        List<Long> sorted = new ArrayList<Long>(latenciesNs);
        Collections.sort(sorted);
        int n = sorted.size();

        double sum = 0;
        for (Long v : sorted) sum += v.doubleValue();
        double mean = sum / n;
        double variance = 0;
        for (Long v : sorted) {
            double d = v.doubleValue() - mean;
            variance += d * d;
        }
        double stddev = Math.sqrt(variance / n);

        long min = sorted.get(0).longValue();
        long max = sorted.get(n - 1).longValue();
        long median = percentile(sorted, 0.50);
        long p95 = percentile(sorted, 0.95);
        long p99 = percentile(sorted, 0.99);
        long peakRssKb = readPeakRssKb();

        PrintWriter out = new PrintWriter(new FileWriter(path));
        try {
            out.println("{");
            out.println("  \"engine\": \"" + engine + "\",");
            out.println("  \"concurrency\": " + concurrency + ",");
            out.println("  \"warmup_iterations\": " + warmup + ",");
            out.println("  \"measured_iterations_per_worker\": " + measured + ",");
            out.println("  \"repetitions\": " + repetitions + ",");
            out.println("  \"sample_count\": " + n + ",");
            out.println("  \"latency_ns\": {");
            out.println("    \"min\": " + min + ",");
            out.println("    \"median\": " + median + ",");
            out.println("    \"mean\": " + Math.round(mean) + ",");
            out.println("    \"p95\": " + p95 + ",");
            out.println("    \"p99\": " + p99 + ",");
            out.println("    \"max\": " + max + ",");
            out.println("    \"stddev\": " + Math.round(stddev));
            out.println("  },");
            out.println("  \"aggregate_throughput_per_sec\": " + aggregateThroughputPerSec + ",");
            out.println("  \"peak_rss_kb\": " + peakRssKb);
            out.println("}");
        } finally {
            out.close();
        }
    }

    private static long percentile(List<Long> sorted, double p) {
        int idx = (int) Math.ceil(p * sorted.size()) - 1;
        if (idx < 0) idx = 0;
        if (idx >= sorted.size()) idx = sorted.size() - 1;
        return sorted.get(idx).longValue();
    }

    private static List<String[]> readTsv(String path) throws Exception {
        List<String[]> rows = new ArrayList<String[]>();
        BufferedReader br = new BufferedReader(new FileReader(path));
        try {
            String line;
            while ((line = br.readLine()) != null) {
                if (line.isEmpty()) continue;
                rows.add(line.split("\t", -1));
            }
        } finally {
            br.close();
        }
        return rows;
    }

    private static String jsonString(String s) {
        if (s == null) return "null";
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }

    private static String toJsonLine(String runId, String hostname, String corpusCommit, String adapterCommit,
                                      String scenarioId, String expected, String actual, boolean correct, String error,
                                      long policyLoadNs, long evalNs) {
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        sb.append("\"run_id\":").append(jsonString(runId)).append(",");
        sb.append("\"engine\":\"sunxacml\",");
        sb.append("\"engine_version\":\"2.0-M1\",");
        sb.append("\"hostname\":").append(jsonString(hostname)).append(",");
        sb.append("\"corpus_commit\":").append(jsonString(corpusCommit)).append(",");
        sb.append("\"adapter_commit\":").append(jsonString(adapterCommit)).append(",");
        sb.append("\"scenario_id\":").append(jsonString(scenarioId)).append(",");
        sb.append("\"expected\":").append(jsonString(expected)).append(",");
        sb.append("\"actual\":").append(jsonString(actual)).append(",");
        sb.append("\"supported\":true,");
        sb.append("\"correct\":").append(correct).append(",");
        sb.append("\"policy_load_ns\":").append(policyLoadNs).append(",");
        sb.append("\"translation_ns\":null,");
        sb.append("\"evaluation_ns\":").append(evalNs).append(",");
        sb.append("\"total_ns\":").append(evalNs).append(",");
        sb.append("\"error\":").append(jsonString(error)).append(",");
        sb.append("\"notes\":null");
        sb.append("}");
        return sb.toString();
    }
}
