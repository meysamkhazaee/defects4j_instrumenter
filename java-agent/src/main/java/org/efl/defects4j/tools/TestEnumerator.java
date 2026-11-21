package org.efl.defects4j.tools;

import java.io.File;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.objectweb.asm.AnnotationVisitor;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

/** Enumerates JUnit 3, JUnit 4, and common JUnit 5 test methods without loading project classes. */
public final class TestEnumerator {
    private static final Set<String> TEST_ANNOTATIONS = new HashSet<String>();
    static {
        TEST_ANNOTATIONS.add("Lorg/junit/Test;");
        TEST_ANNOTATIONS.add("Lorg/junit/jupiter/api/Test;");
        TEST_ANNOTATIONS.add("Lorg/junit/jupiter/params/ParameterizedTest;");
        TEST_ANNOTATIONS.add("Lorg/junit/jupiter/api/RepeatedTest;");
        TEST_ANNOTATIONS.add("Lorg/junit/jupiter/api/TestFactory;");
    }

    private TestEnumerator() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println("Usage: TestEnumerator <test-bin-dirs-file> <allowed-classes-file> <output-file>");
            System.exit(2);
        }
        List<File> roots = readFiles(new File(args[0]));
        Set<String> allowed = readSet(new File(args[1]));
        Map<String, TestClass> classes = new HashMap<String, TestClass>();
        for (File root : roots) {
            if (!root.isDirectory()) continue;
            Files.walk(root.toPath()).filter(path -> path.toString().endsWith(".class")).sorted().forEach(path -> {
                try { scan(path.toFile(), classes); } catch (Exception error) { throw new RuntimeException(error); }
            });
        }
        Set<String> tests = new HashSet<String>();
        for (String className : allowed) {
            collect(className.replace('.', '/'), className, classes, tests, new HashSet<String>());
        }
        List<String> sorted = new ArrayList<String>(tests);
        Collections.sort(sorted);
        Files.write(new File(args[2]).toPath(), sorted, StandardCharsets.UTF_8);
    }

    private static void collect(String internalName, String requestedClass, Map<String, TestClass> classes,
                                Set<String> tests, Set<String> seen) {
        if (!seen.add(internalName)) return;
        TestClass value = classes.get(internalName);
        if (value == null) return;
        for (String method : value.testMethods) tests.add(requestedClass + "::" + method);
        if (value.superName != null && !"java/lang/Object".equals(value.superName)) {
            collect(value.superName, requestedClass, classes, tests, seen);
        }
    }

    private static void scan(File file, Map<String, TestClass> classes) throws Exception {
        try (FileInputStream input = new FileInputStream(file)) {
            ClassReader reader = new ClassReader(input);
            final TestClass testClass = new TestClass(reader.getClassName(), reader.getSuperName());
            reader.accept(new ClassVisitor(Opcodes.ASM5) {
                @Override public MethodVisitor visitMethod(int access, final String name, String descriptor,
                                                           String signature, String[] exceptions) {
                    final boolean junit3 = (access & Opcodes.ACC_PUBLIC) != 0
                            && name.startsWith("test") && "()V".equals(descriptor);
                    return new MethodVisitor(Opcodes.ASM5) {
                        boolean annotated;
                        @Override public AnnotationVisitor visitAnnotation(String descriptor, boolean visible) {
                            if (TEST_ANNOTATIONS.contains(descriptor)) annotated = true;
                            return null;
                        }
                        @Override public void visitEnd() {
                            if (junit3 || annotated) testClass.testMethods.add(name);
                        }
                    };
                }
            }, ClassReader.SKIP_CODE | ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
            classes.put(testClass.name, testClass);
        }
    }

    private static List<File> readFiles(File file) throws Exception {
        List<File> result = new ArrayList<File>();
        for (String line : Files.readAllLines(file.toPath(), StandardCharsets.UTF_8))
            if (!line.trim().isEmpty()) result.add(new File(line.trim()));
        return result;
    }
    private static Set<String> readSet(File file) throws Exception {
        Set<String> result = new HashSet<String>();
        for (String line : Files.readAllLines(file.toPath(), StandardCharsets.UTF_8))
            if (!line.trim().isEmpty()) result.add(line.trim());
        return result;
    }
    private static final class TestClass {
        final String name, superName;
        final Set<String> testMethods = new HashSet<String>();
        TestClass(String name, String superName) { this.name = name; this.superName = superName; }
    }
}
