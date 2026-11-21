package org.efl.defects4j.agent;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

final class PredicateMap {
    private final Map<String, Integer> values;

    private PredicateMap(Map<String, Integer> values) {
        this.values = Collections.unmodifiableMap(values);
    }

    static PredicateMap load(File file) throws IOException {
        Map<String, Integer> result = new HashMap<String, Integer>();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(new FileInputStream(file), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isEmpty() || line.charAt(0) == '#') {
                    continue;
                }
                String[] parts = line.split("\\t", 5);
                if (parts.length != 5) {
                    throw new IOException("Malformed mapping row: " + line);
                }
                int id = Integer.parseInt(parts[0]);
                String key = key(parts[1], parts[2], parts[3], Integer.parseInt(parts[4]));
                result.put(key, Integer.valueOf(id));
            }
        }
        return new PredicateMap(result);
    }

    Integer find(String className, String methodName, String descriptor, int line) {
        return values.get(key(className, methodName, descriptor, line));
    }

    boolean containsClass(String internalName) {
        String prefix = internalName + "\u0000";
        for (String key : values.keySet()) {
            if (key.startsWith(prefix)) {
                return true;
            }
        }
        return false;
    }

    private static String key(String className, String methodName, String descriptor, int line) {
        return className + "\u0000" + methodName + "\u0000" + descriptor + "\u0000" + line;
    }
}
