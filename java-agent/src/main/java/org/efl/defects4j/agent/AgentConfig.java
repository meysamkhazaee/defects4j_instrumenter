package org.efl.defects4j.agent;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.util.Properties;

final class AgentConfig {
    final File mappingFile;
    final File outputDirectory;
    final boolean debug;

    private AgentConfig(File mappingFile, File outputDirectory, boolean debug) {
        this.mappingFile = mappingFile;
        this.outputDirectory = outputDirectory;
        this.debug = debug;
    }

    static AgentConfig load(String path) throws IOException {
        if (path == null || path.trim().isEmpty()) {
            throw new IOException("The EFL Java agent requires a properties-file path as its argument");
        }
        Properties properties = new Properties();
        try (FileInputStream input = new FileInputStream(path)) {
            properties.load(input);
        }
        String mapping = required(properties, "mapping");
        String output = required(properties, "output_dir");
        boolean debug = Boolean.parseBoolean(properties.getProperty("debug", "false"));
        return new AgentConfig(new File(mapping), new File(output), debug);
    }

    private static String required(Properties properties, String key) throws IOException {
        String value = properties.getProperty(key);
        if (value == null || value.trim().isEmpty()) {
            throw new IOException("Missing Java agent property: " + key);
        }
        return value.trim();
    }
}
