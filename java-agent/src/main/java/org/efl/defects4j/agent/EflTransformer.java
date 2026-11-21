package org.efl.defects4j.agent;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

final class EflTransformer implements ClassFileTransformer {
    private static final String RUNTIME = "org/efl/defects4j/agent/TraceRuntime";
    private final PredicateMap mapping;
    private final boolean debug;

    EflTransformer(PredicateMap mapping, boolean debug) {
        this.mapping = mapping;
        this.debug = debug;
    }

    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {
        if (className == null || className.startsWith("org/efl/defects4j/") || !mapping.containsClass(className)) {
            return null;
        }
        try {
            ClassReader reader = new ClassReader(classfileBuffer);
            ClassWriter writer = new SafeClassWriter(reader, ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS, loader);
            reader.accept(new TraceClassVisitor(writer, className, mapping), ClassReader.EXPAND_FRAMES);
            if (debug) {
                System.err.println("[EFL-AGENT] instrumented " + className);
            }
            return writer.toByteArray();
        } catch (Throwable error) {
            System.err.println("[EFL-AGENT] failed to instrument " + className + ": " + error);
            return null;
        }
    }

    private static final class SafeClassWriter extends ClassWriter {
        private final ClassLoader loader;

        SafeClassWriter(ClassReader reader, int flags, ClassLoader loader) {
            super(reader, flags);
            this.loader = loader;
        }

        @Override
        protected String getCommonSuperClass(String type1, String type2) {
            try {
                ClassLoader effective = loader == null ? ClassLoader.getSystemClassLoader() : loader;
                Class<?> left = Class.forName(type1.replace('/', '.'), false, effective);
                Class<?> right = Class.forName(type2.replace('/', '.'), false, effective);
                if (left.isAssignableFrom(right)) return type1;
                if (right.isAssignableFrom(left)) return type2;
                if (left.isInterface() || right.isInterface()) return "java/lang/Object";
                do { left = left.getSuperclass(); } while (left != null && !left.isAssignableFrom(right));
                return left == null ? "java/lang/Object" : left.getName().replace('.', '/');
            } catch (Throwable ignored) {
                return "java/lang/Object";
            }
        }
    }

    private static final class TraceClassVisitor extends ClassVisitor {
        private final String className;
        private final PredicateMap mapping;

        TraceClassVisitor(ClassVisitor delegate, String className, PredicateMap mapping) {
            super(Opcodes.ASM5, delegate);
            this.className = className;
            this.mapping = mapping;
        }

        @Override
        public MethodVisitor visitMethod(int access, String name, String descriptor, String signature, String[] exceptions) {
            MethodVisitor delegate = super.visitMethod(access, name, descriptor, signature, exceptions);
            if ((access & (Opcodes.ACC_ABSTRACT | Opcodes.ACC_NATIVE)) != 0) {
                return delegate;
            }
            return new TraceMethodVisitor(delegate, className, name, descriptor, mapping);
        }
    }

    private static final class TraceMethodVisitor extends MethodVisitor {
        private final String className;
        private final String methodName;
        private final String descriptor;
        private final PredicateMap mapping;
        private int lastInjectedLine = Integer.MIN_VALUE;

        TraceMethodVisitor(MethodVisitor delegate, String className, String methodName, String descriptor, PredicateMap mapping) {
            super(Opcodes.ASM5, delegate);
            this.className = className;
            this.methodName = methodName;
            this.descriptor = descriptor;
            this.mapping = mapping;
        }

        @Override
        public void visitLineNumber(int line, Label start) {
            super.visitLineNumber(line, start);
            if (line == lastInjectedLine) {
                return;
            }
            Integer id = mapping.find(className, methodName, descriptor, line);
            if (id != null) {
                super.visitLdcInsn(id);
                super.visitMethodInsn(Opcodes.INVOKESTATIC, RUNTIME, "hit", "(I)V", false);
                lastInjectedLine = line;
            }
        }
    }
}
