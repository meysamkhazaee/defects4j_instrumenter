package org.efl.defects4j.agent;

import java.io.BufferedOutputStream;
import java.io.DataOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.util.concurrent.atomic.AtomicBoolean;

/** Runtime entry point injected into instrumented project classes. */
public final class TraceRuntime {
    private static final Object LOCK = new Object();
    private static final AtomicBoolean CLOSED = new AtomicBoolean(false);
    private static volatile DataOutputStream output;
    private static volatile File outputFile;
    private static volatile long events;

    private TraceRuntime() {}

    public static void configure(File outputDirectory) throws IOException {
        if (!outputDirectory.isDirectory() && !outputDirectory.mkdirs()) {
            throw new IOException("Cannot create trace directory: " + outputDirectory);
        }
        String process = processId();
        outputFile = new File(outputDirectory, "trace-" + process + "-" + System.nanoTime() + ".bin");
        output = new DataOutputStream(new BufferedOutputStream(new FileOutputStream(outputFile), 1024 * 1024));
        Runtime.getRuntime().addShutdownHook(new Thread(new Runnable() {
            @Override public void run() { close(); }
        }, "efl-trace-shutdown"));
    }

    public static void hit(int predicateId) {
        DataOutputStream stream = output;
        if (stream == null || CLOSED.get()) {
            return;
        }
        synchronized (LOCK) {
            if (CLOSED.get()) {
                return;
            }
            try {
                stream.writeInt(predicateId);
                events++;
            } catch (IOException ignored) {
                // Tracing must never change the behavior of the program under test.
            }
        }
    }

    static void close() {
        if (!CLOSED.compareAndSet(false, true)) {
            return;
        }
        synchronized (LOCK) {
            if (output != null) {
                try {
                    output.flush();
                    output.close();
                } catch (IOException ignored) {
                }
            }
            if (outputFile != null && events == 0L) {
                // Empty agent processes are usually build-tool JVMs; remove their files.
                outputFile.delete();
            }
        }
    }

    private static String processId() {
        String name = ManagementFactory.getRuntimeMXBean().getName();
        int at = name.indexOf('@');
        return at > 0 ? name.substring(0, at) : name.replaceAll("[^A-Za-z0-9_.-]", "_");
    }
}
