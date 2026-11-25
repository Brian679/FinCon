import SwiftUI
import ClientApp

private let serverUrl = Bundle.main.object(forInfoDictionaryKey: "CRDCServerURL") as? String ?? "https://ems.chipingerdc.gov.zw"

@main
struct iOSApp: App {
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            ComposeView()
                .ignoresSafeArea(.keyboard)
                .ignoresSafeArea(edges: .bottom)
        }
        .onChange(of: scenePhase) { phase in
            // Upload work captured offline as soon as the app comes back to the foreground.
            if phase == .active { MainViewControllerKt.syncInBackground(serverUrl: serverUrl) }
        }
    }
}

/// Hosts the shared Kotlin / Compose Multiplatform UI.
struct ComposeView: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> UIViewController {
        MainViewControllerKt.MainViewController(serverUrl: serverUrl)
    }

    func updateUIViewController(_ uiViewController: UIViewController, context: Context) {}
}
