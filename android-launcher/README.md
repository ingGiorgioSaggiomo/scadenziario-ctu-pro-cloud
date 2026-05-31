# Scadenziario CTU Android Launcher

Piccola app Android che apre direttamente lo scadenziario online:

https://scadenziario-ctu-pro.streamlit.app/

## Build APK da GitHub

1. Carica questa cartella sul repository GitHub.
2. Vai in **Actions**.
3. Apri **Android launcher APK**.
4. Premi **Run workflow**.
5. Scarica l'artifact `scadenziario-ctu-android-debug-apk`.
6. Installa `app-debug.apk` sul telefono Android.

Android potrebbe chiedere di autorizzare l'installazione da sorgenti sconosciute.

## Build locale

Richiede Android SDK e Gradle:

```powershell
cd android-launcher
gradle assembleDebug
```

L'APK sara' in:

```text
android-launcher/app/build/outputs/apk/debug/app-debug.apk
```
