import SwiftUI
import WebKit

final class WebViewModel: ObservableObject {

    static let primaryURL  = "https://mygov-hackathon.vercel.app/start"
    static let fallbackURL = "https://mygov-hackathon.vercel.app/source-lens"
    static let allowedHost = "mygov-hackathon.vercel.app"

    @Published var isLoading    = false
    @Published var progress     = 0.0
    @Published var canGoBack    = false
    @Published var canGoForward = false
    @Published var showError    = false
    @Published var showShare    = false
    @Published var currentURL: String?

    weak var webView: WKWebView?

    func handle(_ action: BarAction) {
        switch action {
        case .back:     webView?.goBack()
        case .forward:  webView?.goForward()
        case .refresh:  showError = false; webView?.reload()
        case .external: openExternal()
        case .share:    showShare = true
        }
    }

    func canPerform(_ action: BarAction) -> Bool {
        switch action {
        case .back:    return canGoBack
        case .forward: return canGoForward
        default:       return true
        }
    }

    func reload() {
        showError = false
        if let wv = webView {
            wv.reload()
        } else if let url = URL(string: Self.primaryURL) {
            webView?.load(URLRequest(url: url))
        }
    }

    func openExternal() {
        let raw = currentURL ?? Self.primaryURL
        guard let url = URL(string: raw) else { return }
        UIApplication.shared.open(url)
    }

    func syncNavState() {
        guard let wv = webView else { return }
        canGoBack    = wv.canGoBack
        canGoForward = wv.canGoForward
        currentURL   = wv.url?.absoluteString
    }
}

enum BarAction: CaseIterable {
    case back, forward, refresh, external, share

    var systemImage: String {
        switch self {
        case .back:     return "chevron.left"
        case .forward:  return "chevron.right"
        case .refresh:  return "arrow.clockwise"
        case .external: return "safari"
        case .share:    return "square.and.arrow.up"
        }
    }

    var accessibilityLabel: String {
        switch self {
        case .back:     return "Back"
        case .forward:  return "Forward"
        case .refresh:  return "Refresh"
        case .external: return "Open in Browser"
        case .share:    return "Share"
        }
    }

    var isNavAction: Bool { self == .back || self == .forward }
}
