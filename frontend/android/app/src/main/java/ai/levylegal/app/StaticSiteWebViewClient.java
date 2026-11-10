package ai.levylegal.app;

import android.content.res.AssetManager;
import android.net.Uri;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebViewClient;
import java.io.IOException;
import java.io.InputStream;
import java.util.Map;

/**
 * Serves the app's static pages the way a web host does.
 *
 * The app is a static export with one folder per page (chat/index.html,
 * chat/view/index.html, ...). Capacitor answers every path without a file
 * extension with the root index.html, so a reload on /chat/view/?id=... would
 * render the home page. This rewrites a folder path to its index.html when
 * that file exists and lets Capacitor's own server answer it, which keeps its
 * bridge script injection and headers.
 */
public class StaticSiteWebViewClient extends BridgeWebViewClient {

    private final Bridge bridge;
    private final AssetManager assets;

    public StaticSiteWebViewClient(Bridge bridge) {
        super(bridge);
        this.bridge = bridge;
        this.assets = bridge.getContext().getAssets();
    }

    @Override
    public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
        Uri url = request.getUrl();
        String path = url.getPath();
        if (path != null && !path.equals("/") && isLocal(url) && !lastSegmentHasExtension(path)) {
            String index = (path.endsWith("/") ? path : path + "/") + "index.html";
            if (assetExists("public" + index)) {
                Uri rewritten = url.buildUpon().path(index).build();
                return bridge.getLocalServer().shouldInterceptRequest(new RewrittenRequest(request, rewritten));
            }
        }
        return super.shouldInterceptRequest(view, request);
    }

    private boolean isLocal(Uri url) {
        String host = url.getHost();
        return host != null && host.equals(bridge.getHost());
    }

    private static boolean lastSegmentHasExtension(String path) {
        String trimmed = path.endsWith("/") ? path.substring(0, path.length() - 1) : path;
        String last = trimmed.substring(trimmed.lastIndexOf('/') + 1);
        return last.contains(".");
    }

    private boolean assetExists(String assetPath) {
        try (InputStream ignored = assets.open(assetPath)) {
            return true;
        } catch (IOException e) {
            return false;
        }
    }

    /** The same request with a different URL. */
    private static final class RewrittenRequest implements WebResourceRequest {

        private final WebResourceRequest original;
        private final Uri url;

        RewrittenRequest(WebResourceRequest original, Uri url) {
            this.original = original;
            this.url = url;
        }

        @Override
        public Uri getUrl() {
            return url;
        }

        @Override
        public boolean isForMainFrame() {
            return original.isForMainFrame();
        }

        @Override
        public boolean isRedirect() {
            return original.isRedirect();
        }

        @Override
        public boolean hasGesture() {
            return original.hasGesture();
        }

        @Override
        public String getMethod() {
            return original.getMethod();
        }

        @Override
        public Map<String, String> getRequestHeaders() {
            return original.getRequestHeaders();
        }
    }
}
