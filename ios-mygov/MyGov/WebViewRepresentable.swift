import SwiftUI
import WebKit

struct WebViewRepresentable: UIViewRepresentable {

    @ObservedObject var vm: WebViewModel

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true
        config.mediaTypesRequiringUserActionForPlayback = .all

        let wv = WKWebView(frame: .zero, configuration: config)
        wv.navigationDelegate = context.coordinator
        wv.allowsBackForwardNavigationGestures = false
        wv.scrollView.bounces = true
        wv.isOpaque = false
        let bg = UIColor(red: 0.059, green: 0.071, blue: 0.094, alpha: 1)
        wv.backgroundColor = bg
        wv.scrollView.backgroundColor = bg

        #if DEBUG
        if #available(iOS 16.4, *) { wv.isInspectable = true }
        #endif

        // KVO observers via Swift's typed observe API
        context.coordinator.observations = [
            wv.observe(\.estimatedProgress, options: .new) { [weak vm] wv, _ in
                DispatchQueue.main.async {
                    vm?.progress  = wv.estimatedProgress
                    vm?.isLoading = wv.estimatedProgress < 1.0
                }
            },
            wv.observe(\.canGoBack, options: .new) { [weak vm] wv, _ in
                DispatchQueue.main.async { vm?.canGoBack = wv.canGoBack }
            },
            wv.observe(\.canGoForward, options: .new) { [weak vm] wv, _ in
                DispatchQueue.main.async { vm?.canGoForward = wv.canGoForward }
            },
        ]

        vm.webView = wv
        if let url = URL(string: WebViewModel.primaryURL) {
            wv.load(URLRequest(url: url))
        }
        return wv
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(vm: vm) }

    // ── Coordinator ──────────────────────────────────────────────────

    final class Coordinator: NSObject, WKNavigationDelegate {
        let vm: WebViewModel
        var observations: [NSKeyValueObservation] = []

        init(vm: WebViewModel) { self.vm = vm }

        func webView(_ webView: WKWebView,
                     decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = action.request.url,
                  let scheme = url.scheme?.lowercased()
            else { decisionHandler(.cancel); return }

            if scheme == "about"  { decisionHandler(.allow); return }
            if scheme == "https", url.host?.lowercased() == WebViewModel.allowedHost {
                decisionHandler(.allow); return
            }
            // External URL → open in Safari, block in-app
            UIApplication.shared.open(url)
            decisionHandler(.cancel)
        }

        func webView(_ wv: WKWebView, didStartProvisionalNavigation _: WKNavigation!) {
            DispatchQueue.main.async { self.vm.showError = false }
        }

        func webView(_ wv: WKWebView, didFinish _: WKNavigation!) {
            DispatchQueue.main.async {
                self.vm.isLoading = false
                self.vm.syncNavState()
            }
        }

        func webView(_ wv: WKWebView, didFail _: WKNavigation!, withError error: Error) {
            handle(error)
        }

        func webView(_ wv: WKWebView,
                     didFailProvisionalNavigation _: WKNavigation!,
                     withError error: Error) {
            handle(error)
        }

        private func handle(_ error: Error) {
            guard (error as NSError).code != NSURLErrorCancelled else { return }
            DispatchQueue.main.async {
                self.vm.isLoading = false
                self.vm.showError = true
            }
        }
    }
}
