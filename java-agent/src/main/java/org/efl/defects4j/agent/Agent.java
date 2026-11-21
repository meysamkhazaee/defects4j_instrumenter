package org.efl.defects4j.agent;

import java.io.File;
import java.lang.instrument.Instrumentation;
import java.net.URI;
import java.util.jar.JarFile;

public final class Agent {
    private Agent() {}

    public static void premain(String agentArgs, Instrumentation instrumentation) {
        try {
            appendRuntimeToBootstrap(instrumentation);
            AgentConfig config = AgentConfig.load(agentArgs);
            TraceRuntime.configure(config.outputDirectory);
            PredicateMap mapping = PredicateMap.load(config.mappingFile);
            instrumentation.addTransformer(new EflTransformer(mapping, config.debug), false);
            if (config.debug) {
                System.err.println("[EFL-AGENT] mapping=" + config.mappingFile + " output=" + config.outputDirectory);
            }
        } catch (Throwable error) {
            System.err.println("[EFL-AGENT] initialization failed: " + error);
            error.printStackTrace(System.err);
        }
    }

    private static void appendRuntimeToBootstrap(Instrumentation instrumentation) {
        try {
            URI location = Agent.class.getProtectionDomain().getCodeSource().getLocation().toURI();
            File agentFile = new File(location);
            File runtimeFile = new File(agentFile.getParentFile(), "defects4j-efl-runtime.jar");
            if (runtimeFile.isFile()) {
                instrumentation.appendToBootstrapClassLoaderSearch(new JarFile(runtimeFile));
            }
        } catch (Throwable ignored) {
            // Standard Defects4J runners use parent-first class loading; the agent jar remains a fallback.
        }
    }

}
