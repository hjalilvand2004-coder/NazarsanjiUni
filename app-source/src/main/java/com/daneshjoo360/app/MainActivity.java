package com.daneshjoo360.app;

import android.app.Activity;
import android.content.Context;
import android.graphics.Color;
import android.net.ConnectivityManager;
import android.net.NetworkInfo;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

public class MainActivity extends Activity {
    private WebView webView;
    private ProgressBar progressBar;
    private TextView offlineText;
    private View splashScreen;
    private static final long SPLASH_DELAY = 800;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // پیکربندی window برای Android 10+ (edge-to-edge)
        Window window = getWindow();
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        window.setStatusBarColor(Color.parseColor("#050514"));
        window.setNavigationBarColor(Color.parseColor("#0f0c29"));

        // Android 11+ (API 30+): setDecorFitsSystemWindows
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            try {
                Window.class.getMethod("setDecorFitsSystemWindows", boolean.class).invoke(window, true);
            } catch (Exception e) {
                // ignore
            }
        }

        // ساخت layout اصلی
        FrameLayout layout = new FrameLayout(this);
        FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT);

        // WebView
        webView = new WebView(this);
        layout.addView(webView, params);

        // ProgressBar (بالا)
        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        FrameLayout.LayoutParams pbParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                8);
        progressBar.setLayoutParams(pbParams);
        progressBar.setMax(100);
        progressBar.setProgress(0);
        progressBar.setVisibility(View.GONE);
        layout.addView(progressBar);

        // Splash screen
        splashScreen = new View(this);
        FrameLayout.LayoutParams splashParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT);
        splashScreen.setBackgroundColor(Color.parseColor("#0f0c29"));
        splashScreen.setLayoutParams(splashParams);
        layout.addView(splashScreen);

        // پیام حالت آفلاین
        offlineText = new TextView(this);
        FrameLayout.LayoutParams offlineParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT);
        offlineText.setLayoutParams(offlineParams);
        offlineText.setGravity(android.view.Gravity.CENTER);
        offlineText.setPadding(40, 0, 40, 0);
        offlineText.setTextColor(Color.parseColor("#94a3b8"));
        offlineText.setTextSize(14);
        offlineText.setText("📶 در حال بررسی اتصال اینترنت...");
        offlineText.setVisibility(View.GONE);
        layout.addView(offlineText);

        setContentView(layout);

        // پیکربندی WebView
        configureWebView();

        // بارگذاری URL — به‌صورت hardcode (در زمان build جایگزین می‌شود)
        String url = "https://darsyar360.ir/app";
        if (savedInstanceState != null) {
            webView.restoreState(savedInstanceState);
        } else {
            webView.loadUrl(url);
        }

        // مخفی‌کردن splash بعد از تاخیر
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            if (splashScreen != null && splashScreen.isShown()) {
                splashScreen.setVisibility(View.GONE);
            }
        }, SPLASH_DELAY);
    }

    private void configureWebView() {
        WebSettings settings = webView.getSettings();

        // تنظیمات JavaScript
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);

        // پشتیبانی PWA
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setMediaPlaybackRequiresUserGesture(false);

        // ذخیره‌سازی و کش
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        // setAppCacheEnabled و setAppCachePath در SDK 34 deprecated شده‌اند
        // DOM storage به‌طور خودکار فعال است

        // نمایش منطقی
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setTextZoom(100);

        // پشتیبانی از پروتکل‌های جدید
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        }

        // فعال‌کردن ویژگی‌های مدرن
        settings.setJavaScriptCanOpenWindowsAutomatically(true);
        settings.setSupportMultipleWindows(false);

        // فعال‌کردن کوکی‌ها
        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(webView, true);

        // WebViewClient — مدیریت لینک‌ها
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return false;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                progressBar.setVisibility(View.GONE);
                injectViewport(view);
            }

            @Override
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                super.onReceivedError(view, errorCode, description, failingUrl);
                showOfflineMessage();
            }

            @Override
            public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse errorResponse) {
                super.onReceivedHttpError(view, request, errorResponse);
                if (request.isForMainFrame() && errorResponse.getStatusCode() >= 500) {
                    showOfflineMessage();
                }
            }
        });

        // WebChromeClient — مدیریت progressBar
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                super.onProgressChanged(view, newProgress);
                if (progressBar != null) {
                    progressBar.setVisibility(View.VISIBLE);
                    progressBar.setProgress(newProgress);
                    if (newProgress >= 100) {
                        progressBar.setVisibility(View.GONE);
                    }
                }
            }
        });

        // رنگ پس‌زمینه WebView
        webView.setBackgroundColor(Color.parseColor("#0f0c29"));
    }

    private void injectViewport(WebView view) {
        String css = "javascript:(function(){" +
                "var meta = document.createElement('meta');" +
                "meta.name = 'viewport';" +
                "meta.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover';" +
                "document.getElementsByTagName('head')[0].appendChild(meta);" +
                "})()";
        view.evaluateJavascript(css, null);
    }

    private void showOfflineMessage() {
        if (offlineText != null) {
            offlineText.setText("⚠️ خطا در اتصال به سرور\n\nآدرس سرور را بررسی کنید.\nمطمئن شوید سرور در حال اجراست و موبایل شما به همان شبکه متصل است.");
            offlineText.setVisibility(View.VISIBLE);
            webView.setVisibility(View.GONE);
            if (progressBar != null) progressBar.setVisibility(View.GONE);
            if (splashScreen != null) splashScreen.setVisibility(View.GONE);
        }
    }

    private boolean isOnline() {
        ConnectivityManager cm = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm == null) return false;
        NetworkInfo netInfo = cm.getActiveNetworkInfo();
        return netInfo != null && netInfo.isConnected();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (webView != null) {
            webView.saveState(outState);
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (webView != null) {
            webView.onPause();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) {
            webView.onResume();
        }
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
