package io.github.kerxs.xxtplus

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.Log
import java.security.KeyStore
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * The key that encrypts the account, password, API keys and saved cookies (core/secret.py).
 *
 * A random 256-bit data key is kept in the app's preferences, wrapped (AES-GCM) by a key that
 * lives in the Android Keystore and never leaves it. Python gets the unwrapped data key as hex
 * (XXTPLUS_DATA_KEY), in the UI process and in the :worker process alike.
 */
object DataKey {
    private const val ALIAS = "xxtplus_data_key_wrap"
    private const val PREFS = "secure"
    private const val ENTRY = "data_key"
    private const val TAG = "DataKey"

    @Volatile private var cached: String? = null

    /** Hex data key, or "" when the Keystore is unavailable (values then stay plain text, as before). */
    @Synchronized
    fun hex(ctx: Context): String {
        cached?.let { return it }
        val value = runCatching { load(ctx.applicationContext) }
            .onFailure { Log.w(TAG, "data key unavailable: ${it.javaClass.simpleName}") }
            .getOrDefault("")
        cached = value
        return value
    }

    private fun load(ctx: Context): String {
        val prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val wrap = wrappingKey()
        prefs.getString(ENTRY, null)?.let { stored ->
            val raw = Base64.decode(stored, Base64.NO_WRAP)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, wrap, GCMParameterSpec(128, raw, 0, 12))
            return cipher.doFinal(raw, 12, raw.size - 12).toHex()
        }
        val key = ByteArray(32).also { SecureRandom().nextBytes(it) }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, wrap)
        val stored = cipher.iv + cipher.doFinal(key)
        // commit(): the :worker process may read it right after the UI process created it
        prefs.edit().putString(ENTRY, Base64.encodeToString(stored, Base64.NO_WRAP)).commit()
        return key.toHex()
    }

    private fun wrappingKey(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return generator.generateKey()
    }

    private fun ByteArray.toHex() = joinToString("") { "%02x".format(it) }
}
