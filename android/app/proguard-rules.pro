# Code shrinking for the release APK (1.3.0): the app's own classes stay as they are — the
# Python side calls into them by name through Chaquopy (the event sink in TaskService, the
# bridge objects), which R8 cannot see. What shrinks is the libraries: Compose, the extended
# Material icon set (several thousand classes, a few dozen used) and the Kotlin runtime.
-keep class io.github.kerxs.xxtplus.** { *; }
-keepattributes *Annotation*, Signature, InnerClasses, EnclosingMethod

# Chaquopy ships its own rules for com.chaquo.python; these are optional classes it references.
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
