import SwiftUI

struct ContentView: View {

    @StateObject private var vm = WebViewModel()

    private let barBg   = Color(red: 0.082, green: 0.337, blue: 0.753)
    private let pageBg  = Color(red: 0.059, green: 0.071, blue: 0.094)
    private let bottomBg = Color(red: 0.118, green: 0.118, blue: 0.176)
    private let divider = Color(red: 0.141, green: 0.188, blue: 0.314)
    private let muted   = Color(red: 0.580, green: 0.635, blue: 0.722)

    var body: some View {
        VStack(spacing: 0) {

            // ── App bar ─────────────────────────────────────────────
            HStack {
                Text("MyGov")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(.white)
                Spacer()
            }
            .padding(.horizontal, 16)
            .frame(height: 50)
            .background(barBg)

            // ── Loading bar ─────────────────────────────────────────
            ZStack(alignment: .top) {
                if vm.isLoading {
                    ProgressView(value: vm.progress, total: 1.0)
                        .progressViewStyle(.linear)
                        .tint(.white)
                        .frame(height: 3)
                }
            }
            .frame(height: vm.isLoading ? 3 : 0)

            // ── Main content ────────────────────────────────────────
            ZStack {
                WebViewRepresentable(vm: vm)
                    .opacity(vm.showError ? 0 : 1)
                    .accessibility(hidden: vm.showError)

                if vm.showError {
                    ErrorView(vm: vm, pageBg: pageBg, muted: muted)
                        .transition(.opacity)
                }
            }

            // ── Divider ─────────────────────────────────────────────
            divider.frame(height: 1)

            // ── Bottom control bar ──────────────────────────────────
            HStack(spacing: 0) {
                ForEach(BarAction.allCases, id: \.self) { action in
                    Button {
                        vm.handle(action)
                    } label: {
                        Image(systemName: action.systemImage)
                            .font(.system(size: 17, weight: .regular))
                            .foregroundColor(
                                (action.isNavAction && !vm.canPerform(action))
                                    ? .white.opacity(0.28)
                                    : .white
                            )
                            .frame(maxWidth: .infinity, minHeight: 52)
                            .contentShape(Rectangle())
                    }
                    .disabled(action.isNavAction && !vm.canPerform(action))
                    .accessibilityLabel(action.accessibilityLabel)
                }
            }
            .background(bottomBg)

        }
        .ignoresSafeArea(edges: .bottom)
        .background(pageBg)
        .sheet(isPresented: $vm.showShare) {
            let url = URL(string: vm.currentURL ?? WebViewModel.primaryURL)
                   ?? URL(string: WebViewModel.primaryURL)!
            ShareSheet(items: [url])
                .ignoresSafeArea()
        }
    }
}

// ── Error overlay ─────────────────────────────────────────────────────

private struct ErrorView: View {
    @ObservedObject var vm: WebViewModel
    let pageBg: Color
    let muted: Color

    var body: some View {
        VStack(spacing: 16) {
            Text("Connection failed")
                .font(.title2.bold())
                .foregroundColor(.white)
            Text("Could not load MyGov. Check your connection and try again.")
                .font(.subheadline)
                .foregroundColor(muted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
            Button("Retry") { vm.reload() }
                .buttonStyle(.borderedProminent)
                .tint(Color(red: 0.114, green: 0.306, blue: 0.847))
            Button("Open in Browser") { vm.openExternal() }
                .buttonStyle(.bordered)
                .tint(.white)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(pageBg)
    }
}

// ── System share sheet ────────────────────────────────────────────────

struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}
