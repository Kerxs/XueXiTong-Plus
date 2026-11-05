package io.github.kerxs.xxtplus

import android.content.Context
import android.graphics.Matrix
import android.graphics.SurfaceTexture
import android.media.MediaPlayer
import android.net.Uri
import android.util.Log
import android.view.Surface
import android.view.TextureView
import kotlin.math.abs

/**
 * 视频预览 on the phone: the system media player drawing into a TextureView, muted.
 *
 * The 学习通 video CDN (s1/s2.cldisk.com) refuses requests without the player page's Referer.
 * A WebView page cannot be made to send it, so the player requests the video itself with the
 * same Referer / User-Agent the desktop's local proxy uses (ui/videoproxy.py — keep in sync).
 * Muted and never asks for audio focus, so the user's music keeps playing.
 */
class PreviewPlayer(ctx: Context) : TextureView(ctx), TextureView.SurfaceTextureListener {
    companion object {
        const val REFERER = "https://mooc1.chaoxing.com/ananas/modules/video/index.html?v=2025-0725-1842"
        const val USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) " +
            "Chrome/118.0.0.0 Safari/537.36"
        private const val TAG = "PreviewPlayer"
    }

    /** "loading" | "playing" | "retrying" | "error" */
    var onState: (String) -> Unit = {}
    /** Called after 3 failures in a row: the address may have expired (the app asks for a new one). */
    var onGiveUp: () -> Unit = {}

    private val handler = android.os.Handler(android.os.Looper.getMainLooper())
    private var failures = 0
    private var position = 0.0
    private val retry = Runnable { reopen() }

    private var player: MediaPlayer? = null
    private var prepared = false
    private var surface: Surface? = null
    private var source = ""
    private var sources: List<String> = emptyList()   // backup addresses, tried in order on errors
    private var sourceIndex = 0
    private var startAt = 0.0
    private var videoW = 0
    private var videoH = 0

    init {
        surfaceTextureListener = this
        isOpaque = false
    }

    /** Show this video (its addresses, best first), starting at `at` seconds. The same video again is ignored. */
    fun show(urls: List<String>, at: Double) {
        if (at >= 0) position = at
        if (urls.isEmpty() || urls.first() == sources.firstOrNull()) return
        sources = urls
        sourceIndex = 0
        source = urls.first()
        failures = 0
        handler.removeCallbacks(retry)
        startAt = at.coerceAtLeast(0.0)
        open()
    }

    /** Try the same address again from where the task is (after an error). */
    private fun reopen() {
        startAt = position
        open()
    }

    private fun failed() {
        // A backup address first (no waiting); only when all of them failed, wait and start over.
        if (sourceIndex + 1 < sources.size) {
            sourceIndex++
            source = sources[sourceIndex]
            Log.w(TAG, "trying backup address ${sourceIndex + 1}/${sources.size}")
            handler.removeCallbacks(retry)
            handler.post(retry)
            return
        }
        sourceIndex = 0
        source = sources.firstOrNull() ?: source
        failures++
        if (failures == 3) onGiveUp()
        // 2, 4, 8, 16, 30, 30 ... seconds: it never gives up while the video is on screen
        val waitMs = minOf(30_000L, 2_000L shl minOf(failures - 1, 4))
        onState(if (failures >= 3) "error" else "retrying")
        handler.removeCallbacks(retry)
        handler.postDelayed(retry, waitMs)
    }

    /** Follow the task: keep within 3 s of its position, pause while the task is paused. */
    fun sync(position: Double, paused: Boolean) {
        if (position >= 0) this.position = position
        val mp = player ?: return
        if (!prepared) return
        runCatching {
            if (paused) {
                if (mp.isPlaying) mp.pause()
                return
            }
            if (position >= 0 && abs(mp.currentPosition / 1000.0 - position) > 3) mp.seekTo((position * 1000).toInt())
            if (!mp.isPlaying) mp.start()
        }
    }

    fun release() {
        handler.removeCallbacks(retry)
        prepared = false
        player?.let { mp -> runCatching { mp.reset(); mp.release() } }
        player = null
    }

    private fun open() {
        val s = surface ?: return       // opened again once the surface exists
        if (source.isEmpty()) return
        release()
        onState("loading")
        val mp = MediaPlayer()
        player = mp
        try {
            mp.setSurface(s)
            mp.setVolume(0f, 0f)
            mp.setDataSource(context, Uri.parse(source), mapOf("Referer" to REFERER, "User-Agent" to USER_AGENT))
            mp.setOnPreparedListener {
                if (player !== it) return@setOnPreparedListener
                prepared = true
                failures = 0
                it.setVolume(0f, 0f)
                if (startAt > 0) it.seekTo((startAt * 1000).toInt())
                it.start()
                onState("playing")
            }
            mp.setOnVideoSizeChangedListener { _, w, h -> videoW = w; videoH = h; fit() }
            mp.setOnErrorListener { it, what, extra ->
                if (player === it) {
                    Log.w(TAG, "playback error $what/$extra")
                    failed()
                }
                true
            }
            mp.prepareAsync()
        } catch (e: Exception) {
            Log.w(TAG, "cannot open the video: ${e.javaClass.simpleName}")
            failed()
        }
    }

    /** Letterbox: keep the video's aspect ratio inside the view. */
    private fun fit() {
        if (videoW <= 0 || videoH <= 0 || width <= 0 || height <= 0) return
        val view = width.toFloat() / height
        val video = videoW.toFloat() / videoH
        val sx = if (video > view) 1f else video / view
        val sy = if (video > view) view / video else 1f
        setTransform(Matrix().apply { setScale(sx, sy, width / 2f, height / 2f) })
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        fit()
    }

    override fun onSurfaceTextureAvailable(st: SurfaceTexture, width: Int, height: Int) {
        surface = Surface(st)
        open()
    }

    override fun onSurfaceTextureSizeChanged(st: SurfaceTexture, width: Int, height: Int) = fit()

    override fun onSurfaceTextureDestroyed(st: SurfaceTexture): Boolean {
        release()
        surface?.release()
        surface = null
        source = ""             // the next show() of the same address opens it again
        startAt = 0.0
        return true
    }

    override fun onSurfaceTextureUpdated(st: SurfaceTexture) {}
}
