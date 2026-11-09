package ai.levylegal.app;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // Reloads and deep links land on the right page (see StaticSiteWebViewClient).
        bridge.setWebViewClient(new StaticSiteWebViewClient(bridge));
    }
}
