package com.calorietracker.app;

import android.annotation.SuppressLint;
import android.graphics.Color;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.webkit.SslErrorHandler;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 应用唯一界面：内嵌 WebView 显示本地 Python 后端的静态前端。
 *
 * 启动顺序：
 *   1. 显示加载页；
 *   2. 后台线程启动 Chaquopy 与本地 HTTP 服务（127.0.0.1:8787）；
 *   3. 服务就绪后用 WebView 打开 http://127.0.0.1:8787/。
 *
 * 数据（ct.db / config.json）保存在应用私有目录 files/data 下，随应用卸载删除。
 */
public class MainActivity extends AppCompatActivity {

    private static final String TAG = "CalorieTracker";
    private static final int LOOPBACK_PORT = 8787;

    private WebView web;
    private TextView status;
    private volatile boolean serverReady = false;
    private volatile String startupError = null;

    @Override
    @SuppressLint("SetJavaScriptEnabled")
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        web = findViewById(R.id.webview);
        status = findViewById(R.id.status);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);          // 前端用 localStorage 记住后端地址
        s.setDatabaseEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);
        s.setSupportZoom(false);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);
        s.setMediaPlaybackRequiresUserGesture(true);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        s.setTextZoom(100);

        web.setBackgroundColor(Color.parseColor("#0f1115"));
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                String host = u.getHost() == null ? "" : u.getHost();
                // 只允许本地地址在 WebView 内打开，其余交给系统处理。
                if ("127.0.0.1".equals(host) || "localhost".equals(host)) {
                    return false;
                }
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (serverReady) {
                    findViewById(R.id.loading).setVisibility(View.GONE);
                }
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame() && !serverReady) {
                    showFailure("网页加载失败：" + error.getDescription());
                }
            }

            @Override
            public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                handler.cancel();
            }
        });

        startPythonBackend();
    }

    /** 启动 Chaquopy 与本地服务；整个过程放在后台线程，避免阻塞界面。 */
    private void startPythonBackend() {
        final AtomicBoolean started = new AtomicBoolean(false);
        new Thread(() -> {
            try {
                if (!Python.isStarted()) {
                    Python.start(new AndroidPlatform(getApplicationContext()));
                }
                Python py = Python.getInstance();
                PyObject bootstrap = py.getModule("ctserver");

                // 前端静态文件随 app.imy 打包，运行时由 Chaquopy 解压到应用私有目录。
                // Platform.getPath() 会返回这些解压目录（以系统路径分隔符连接），
                // 把它们交给 Python，用于定位 frontend/。
                //
                // 注意：必须传 String[] 而不是 List/ArrayList —— Chaquopy 只把
                // java.util.ArrayList 包装成不可迭代的代理对象，Python 侧遍历会抛
                // "TypeError: 'ArrayList' object is not iterable"；数组会被转换成
                // 原生 Python list。
                String[] extraDirs = new String[0];
                try {
                    String paths = py.getPlatform().getPath();
                    if (paths != null && !paths.isEmpty()) {
                        List<String> parts = new ArrayList<>();
                        for (String part : paths.split(java.util.regex.Pattern.quote(File.pathSeparator))) {
                            if (!part.isEmpty()) parts.add(part);
                        }
                        extraDirs = parts.toArray(new String[0]);
                    }
                } catch (Throwable t) {
                    Log.w(TAG, "读取 Chaquopy 解压路径失败，将回退到默认候选路径", t);
                }
                Log.i(TAG, "Chaquopy 解压路径：" + java.util.Arrays.toString(extraDirs));

                String info = bootstrap.callAttr("start", getFilesDir().getAbsolutePath(),
                        (long) LOOPBACK_PORT, extraDirs).toString();
                Log.i(TAG, "后端已启动：" + info);
                started.set(true);
            } catch (Throwable t) {
                Log.e(TAG, "后端启动失败", t);
                startupError = describe(t);
            }
            runOnUiThread(this::waitForServer);
        }, "ct-python-start").start();
    }

    /** 轮询 /api/health，确认服务真的在监听后再打开页面。 */
    private void waitForServer() {
        if (startupError != null) {
            showFailure(startupError);
            return;
        }
        final String base = "http://127.0.0.1:" + LOOPBACK_PORT;
        final long deadline = System.currentTimeMillis() + 40_000;
        final TextView tv = status;
        new Thread(() -> {
            String lastError = null;
            while (System.currentTimeMillis() < deadline) {
                try {
                    java.net.HttpURLConnection c =
                            (java.net.HttpURLConnection) new java.net.URL(base + "/api/health").openConnection();
                    c.setConnectTimeout(1500);
                    c.setReadTimeout(1500);
                    c.setRequestMethod("GET");
                    int code = c.getResponseCode();
                    c.disconnect();
                    if (code == 200) {
                        final String url = base + "/";
                        runOnUiThread(() -> {
                            serverReady = true;
                            tv.setText("正在打开界面…");
                            web.loadUrl(url);
                        });
                        return;
                    }
                    lastError = "健康检查返回 " + code;
                } catch (Exception e) {
                    lastError = e.getClass().getSimpleName() + ": " + e.getMessage();
                }
                try {
                    Thread.sleep(400);
                } catch (InterruptedException ignored) {
                    return;
                }
            }
            final String msg = lastError;
            runOnUiThread(() -> showFailure("本地服务未在 40 秒内就绪。\n" + (msg == null ? "" : msg)));
        }, "ct-health-wait").start();
    }

    private void showFailure(String detail) {
        status.setText("启动失败");
        String html = "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
                + "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
                + "<style>body{background:#0f1115;color:#e6e6e6;font-family:sans-serif;padding:24px;line-height:1.6}"
                + "h1{font-size:18px;color:#ff6b6b}pre{white-space:pre-wrap;word-break:break-all;background:#171a21;"
                + "padding:12px;border-radius:8px;font-size:12px;color:#c9d1d9}"
                + ".hint{color:#8b949e;font-size:13px}</style></head><body>"
                + "<h1>无法启动内置后端</h1>"
                + "<p class=\"hint\">应用界面已打开，但本地 Python 服务没有响应。可以把下面的信息反馈给开发者：</p>"
                + "<pre>" + escape(detail) + "</pre>"
                + "<p class=\"hint\">可尝试：确认已授予网络权限、重启应用、或查看日志（tag: CalorieTracker / python.stderr）。</p>"
                + "</body></html>";
        serverReady = true; // 避免 onReceivedError 再次覆盖错误页
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null);
    }

    private static String escape(String s) {
        if (s == null) return "";
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
    }

    private static String describe(Throwable t) {
        StringBuilder sb = new StringBuilder(t.getClass().getName());
        if (t.getMessage() != null) sb.append(": ").append(t.getMessage());
        Throwable cause = t.getCause();
        int depth = 0;
        while (cause != null && depth++ < 4) {
            sb.append("\n  ← ").append(cause.getClass().getName());
            if (cause.getMessage() != null) sb.append(": ").append(cause.getMessage());
            cause = cause.getCause();
        }
        return sb.toString();
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        try {
            if (Python.isStarted()) {
                PyObject bootstrap = Python.getInstance().getModule("ctserver");
                bootstrap.callAttr("stop");
            }
        } catch (Throwable t) {
            Log.w(TAG, "关闭本地服务时出错", t);
        }
        super.onDestroy();
    }
}
