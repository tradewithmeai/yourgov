package uk.mygov.mobile

import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.appbar.MaterialToolbar

class MainActivity : AppCompatActivity() {

    companion object {
        private const val PRIMARY_URL = "https://yourgov.solvx.uk/start"
        private const val FALLBACK_URL = "https://yourgov.solvx.uk/source-lens"
        private const val ALLOWED_HOST = "yourgov.solvx.uk"
    }

    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private lateinit var errorLayout: View
    private lateinit var errorMessage: TextView
    private lateinit var btnBack: ImageButton
    private lateinit var btnForward: ImageButton

    private var initialLoadFailed = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val toolbar = findViewById<MaterialToolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)

        webView = findViewById(R.id.webView)
        progressBar = findViewById(R.id.progressBar)
        errorLayout = findViewById(R.id.errorLayout)
        errorMessage = findViewById(R.id.errorMessage)
        btnBack = findViewById(R.id.btnBack)
        btnForward = findViewById(R.id.btnForward)

        configureWebView()
        setupControls()
        setupBackPress()

        if (savedInstanceState != null) {
            webView.restoreState(savedInstanceState)
        } else {
            webView.loadUrl(PRIMARY_URL)
        }
    }

    private fun configureWebView() {
        with(webView.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            setSupportZoom(false)
            builtInZoomControls = false
            displayZoomControls = false
            mediaPlaybackRequiresUserGesture = true
            cacheMode = WebSettings.LOAD_DEFAULT
            useWideViewPort = true
            loadWithOverviewMode = true
        }

        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)

        WebView.startSafeBrowsing(this) { _ -> }

        webView.webViewClient = object : WebViewClient() {

            override fun shouldOverrideUrlLoading(
                view: WebView,
                request: WebResourceRequest
            ): Boolean {
                val url = request.url.toString()
                return if (isAllowedUrl(url)) {
                    false
                } else {
                    openInBrowser(url)
                    true
                }
            }

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                initialLoadFailed = false
                progressBar.visibility = View.VISIBLE
                hideError()
            }

            override fun onPageFinished(view: WebView, url: String) {
                progressBar.visibility = View.GONE
                updateNavButtons()
            }

            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: WebResourceError
            ) {
                if (request.isForMainFrame) {
                    progressBar.visibility = View.GONE
                    if (!initialLoadFailed) {
                        initialLoadFailed = true
                        showError(getString(R.string.error_message))
                    }
                }
            }

            override fun onReceivedHttpError(
                view: WebView,
                request: WebResourceRequest,
                errorResponse: WebResourceResponse
            ) {
                if (request.isForMainFrame && errorResponse.statusCode >= 500) {
                    progressBar.visibility = View.GONE
                    showError(getString(R.string.error_message))
                }
            }

            override fun onRenderProcessGone(
                view: WebView,
                detail: RenderProcessGoneDetail
            ): Boolean {
                webView.loadUrl(PRIMARY_URL)
                return true
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, newProgress: Int) {
                progressBar.progress = newProgress
                progressBar.visibility = if (newProgress < 100) View.VISIBLE else View.GONE
            }
        }
    }

    private fun setupControls() {
        btnBack.setOnClickListener {
            if (webView.canGoBack()) webView.goBack()
        }
        btnForward.setOnClickListener {
            if (webView.canGoForward()) webView.goForward()
        }
        findViewById<ImageButton>(R.id.btnRefresh).setOnClickListener {
            hideError()
            webView.reload()
        }
        findViewById<ImageButton>(R.id.btnExternal).setOnClickListener {
            openInBrowser(webView.url ?: PRIMARY_URL)
        }
        findViewById<ImageButton>(R.id.btnShare).setOnClickListener {
            shareUrl(webView.url ?: PRIMARY_URL)
        }
        findViewById<Button>(R.id.btnRetry).setOnClickListener {
            initialLoadFailed = false
            hideError()
            webView.loadUrl(PRIMARY_URL)
        }
        findViewById<Button>(R.id.btnErrorBrowser).setOnClickListener {
            openInBrowser(FALLBACK_URL)
        }

        updateNavButtons()
    }

    private fun setupBackPress() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) {
                    webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })
    }

    /**
     * Only allows HTTPS navigation to yourgov.solvx.uk.
     * Everything else is opened in the external browser.
     */
    private fun isAllowedUrl(url: String): Boolean {
        return try {
            val uri = Uri.parse(url)
            uri.scheme?.lowercase() == "https" && uri.host?.lowercase() == ALLOWED_HOST
        } catch (e: Exception) {
            false
        }
    }

    private fun openInBrowser(url: String) {
        try {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            startActivity(intent)
        } catch (_: Exception) {
            // No browser available — silently swallow
        }
    }

    private fun shareUrl(url: String) {
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, url)
            putExtra(Intent.EXTRA_SUBJECT, getString(R.string.app_name))
        }
        startActivity(Intent.createChooser(intent, getString(R.string.share_via)))
    }

    private fun showError(message: String) {
        webView.visibility = View.GONE
        errorLayout.visibility = View.VISIBLE
        errorMessage.text = message
    }

    private fun hideError() {
        webView.visibility = View.VISIBLE
        errorLayout.visibility = View.GONE
    }

    private fun updateNavButtons() {
        val canBack = webView.canGoBack()
        btnBack.isEnabled = canBack
        btnBack.alpha = if (canBack) 1f else 0.35f

        val canFwd = webView.canGoForward()
        btnForward.isEnabled = canFwd
        btnForward.alpha = if (canFwd) 1f else 0.35f
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        webView.saveState(outState)
    }

    override fun onPause() {
        super.onPause()
        webView.onPause()
    }

    override fun onResume() {
        super.onResume()
        webView.onResume()
    }

    override fun onDestroy() {
        webView.destroy()
        super.onDestroy()
    }
}
