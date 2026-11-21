package org.efl.defects4j.tools;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

/** Scans compiled production classes and creates deterministic line predicates. */
public final class ClassScanner {
    private ClassScanner() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 5) {
            System.err.println("Usage: ClassScanner <bin-dirs-file> <class-filter-file|-> <source-root> <mapping.tsv> <source_map.csv>");
            System.exit(2);
        }
        List<File> roots = readFiles(new File(args[0]));
        Set<String> filter = "-".equals(args[1]) ? Collections.<String>emptySet() : readSet(new File(args[1]));
        String sourceRoot = args[2].replace('\\', '/').replaceAll("/+$", "");
        List<Row> rows = new ArrayList<Row>();
        for (File root : roots) {
            if (!root.isDirectory()) {
                continue;
            }
            Files.walk(root.toPath())
                    .filter(path -> path.toString().endsWith(".class"))
                    .sorted()
                    .forEach(path -> scan(root.toPath(), path, filter, sourceRoot, rows));
        }
        Collections.sort(rows);
        write(rows, new File(args[3]), new File(args[4]));
    }

    private static void scan(Path root, Path classFile, Set<String> filter, String sourceRoot, List<Row> rows) {
        try (FileInputStream input = new FileInputStream(classFile.toFile())) {
            ClassReader reader = new ClassReader(input);
            final String internalName = reader.getClassName();
            final String dotted = internalName.replace('/', '.');
            if (!filter.isEmpty() && !matches(filter, dotted)) {
                return;
            }
            reader.accept(new ClassVisitor(Opcodes.ASM5) {
                String sourceFile;
                @Override public void visitSource(String source, String debug) { sourceFile = source; }
                @Override public MethodVisitor visitMethod(int access, String name, String descriptor, String signature, String[] exceptions) {
                    if ((access & (Opcodes.ACC_ABSTRACT | Opcodes.ACC_NATIVE)) != 0) {
                        return null;
                    }
                    return new MethodVisitor(Opcodes.ASM5) {
                        final Set<Integer> seen = new HashSet<Integer>();
                        @Override public void visitLineNumber(int line, Label start) {
                            if (line <= 0 || !seen.add(Integer.valueOf(line))) {
                                return;
                            }
                            String packagePath = internalName.contains("/")
                                    ? internalName.substring(0, internalName.lastIndexOf('/') + 1) : "";
                            String source = sourceFile == null ? simpleName(internalName) + ".java" : sourceFile;
                            String file = sourceRoot.isEmpty() ? packagePath + source : sourceRoot + "/" + packagePath + source;
                            rows.add(new Row(internalName, name, descriptor, line, file));
                        }
                    };
                }
            }, ClassReader.SKIP_FRAMES);
        } catch (IOException error) {
            throw new RuntimeException("Cannot scan " + classFile + ": " + error, error);
        }
    }

    private static boolean matches(Set<String> filter, String className) {
        if (filter.contains(className)) {
            return true;
        }
        int dollar = className.indexOf('$');
        return dollar > 0 && filter.contains(className.substring(0, dollar));
    }

    private static String simpleName(String internalName) {
        int slash = internalName.lastIndexOf('/');
        String value = slash >= 0 ? internalName.substring(slash + 1) : internalName;
        int dollar = value.indexOf('$');
        return dollar > 0 ? value.substring(0, dollar) : value;
    }

    private static void write(List<Row> rows, File mapping, File sourceMap) throws IOException {
        mapping.getParentFile().mkdirs();
        sourceMap.getParentFile().mkdirs();
        try (BufferedWriter map = writer(mapping); BufferedWriter csv = writer(sourceMap)) {
            csv.write("predicate,id,file,line,column,function,class,method,descriptor,event_type\n");
            int id = 1;
            for (Row row : rows) {
                map.write(id + "\t" + row.className + "\t" + row.method + "\t" + row.descriptor + "\t" + row.line + "\n");
                csv.write(csv("P" + id) + "," + id + "," + csv(row.file) + "," + row.line + ",0,"
                        + csv(row.className.replace('/', '.') + "#" + row.method) + ","
                        + csv(row.className.replace('/', '.')) + "," + csv(row.method) + ","
                        + csv(row.descriptor) + ",line\n");
                id++;
            }
        }
    }

    private static BufferedWriter writer(File file) throws IOException {
        return new BufferedWriter(new OutputStreamWriter(new FileOutputStream(file), StandardCharsets.UTF_8));
    }

    private static String csv(String value) {
        return "\"" + value.replace("\"", "\"\"") + "\"";
    }

    private static List<File> readFiles(File file) throws IOException {
        List<File> result = new ArrayList<File>();
        for (String line : Files.readAllLines(file.toPath(), StandardCharsets.UTF_8)) {
            if (!line.trim().isEmpty()) result.add(new File(line.trim()));
        }
        return result;
    }

    private static Set<String> readSet(File file) throws IOException {
        Set<String> result = new HashSet<String>();
        for (String line : Files.readAllLines(file.toPath(), StandardCharsets.UTF_8)) {
            if (!line.trim().isEmpty()) result.add(line.trim());
        }
        return result;
    }

    private static final class Row implements Comparable<Row> {
        final String className, method, descriptor, file;
        final int line;
        Row(String className, String method, String descriptor, int line, String file) {
            this.className = className; this.method = method; this.descriptor = descriptor; this.line = line; this.file = file;
        }
        @Override public int compareTo(Row other) {
            int value = className.compareTo(other.className);
            if (value == 0) value = method.compareTo(other.method);
            if (value == 0) value = descriptor.compareTo(other.descriptor);
            if (value == 0) value = Integer.compare(line, other.line);
            return value;
        }
    }
}
