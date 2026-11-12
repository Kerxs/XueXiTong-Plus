import configparser
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packaging"))

from prune import is_unused  # noqa: E402
from ui import winsetup  # noqa: E402


class PruneRulesTestCase(unittest.TestCase):
    def test_keeps_what_the_app_loads(self):
        keep = [
            "PySide6/Qt6Core.dll", "PySide6/Qt6Gui.dll", "PySide6/Qt6Qml.dll", "PySide6/Qt6Quick.dll",
            "PySide6/Qt6QuickControls2.dll", "PySide6/Qt6QuickControls2FluentWinUI3.dll",
            "PySide6/Qt6QuickControls2FluentWinUI3StyleImpl.dll", "PySide6/Qt6QuickControls2Basic.dll",
            "PySide6/Qt6QuickTemplates2.dll", "PySide6/Qt6QuickLayouts.dll", "PySide6/Qt6WebView.dll",
            "PySide6/Qt6WebViewQuick.dll", "PySide6/Qt6Network.dll", "PySide6/Qt6Svg.dll", "PySide6/Qt6OpenGL.dll",
            "PySide6/Qt6Widgets.dll", "PySide6/QtQuick.pyd", "PySide6/QtOpenGL.pyd", "PySide6/QtQml.pyd", "PySide6/QtWebView.pyd",
            "PySide6/qml/QtQuick/Controls/FluentWinUI3/Button.qml",
            "PySide6/qml/QtQuick/Controls/Basic/Button.qml",
            "PySide6/qml/QtQuick/Controls/Fusion/qmldir", "PySide6/qml/QtQuick/Controls/Fusion/impl/qmldir",
            "PySide6/Qt6QuickControls2Fusion.dll", "PySide6/Qt6QuickControls2FusionStyleImpl.dll",
            "PySide6/qml/QtQuick/Effects/qmldir", "PySide6/qml/QtQuick/Shapes/qmldir", "PySide6/Qt6QuickEffects.dll",
            "PySide6/Qt6QuickShapes.dll",
            "PySide6/qml/QtQuick/Controls/impl/qmldir",
            "PySide6/qml/QtQuick/Layouts/qmldir", "PySide6/qml/QtCore/qmldir", "PySide6/qml/QtWebView/qmldir",
            "PySide6/plugins/platforms/qwindows.dll", "PySide6/plugins/webview/qtwebview_webview2.dll",
            "ddddocr/common_old.onnx", "resource/font_map_table.json",
            "PySide6/Qt6QmlMeta.dll", "PySide6/Qt6QmlCore.dll", "PySide6/Qt6QmlNetwork.dll",
            "PySide6/plugins/imageformats/qico.dll", "PySide6/plugins/imageformats/qjpeg.dll",
            "PySide6/plugins/imageformats/qsvg.dll", "PySide6/plugins/iconengines/qsvgicon.dll",
            "PySide6/plugins/tls/qschannelbackend.dll", "PySide6/plugins/styles/qmodernwindowsstyle.dll",
        ]
        for name in keep:
            self.assertFalse(is_unused(name), name)

    def test_drops_unused_parts(self):
        drop = [
            "PySide6/opengl32sw.dll", "PySide6/translations/qt_zh_CN.qm", "PySide6/Qt6Quick3D.dll",
            "PySide6/Qt6Quick3DPhysics.dll", "PySide6/Qt63DCore.dll", "PySide6/Qt6Charts.dll",
            "PySide6/Qt6ShaderTools.dll", "PySide6/Qt6QuickControls2Material.dll",
            "PySide6/qml/QtQuick3D/qmldir", "PySide6/qml/QtQuick/Controls/Material/Button.qml",
            "PySide6/qml/Qt/labs/settings/qmldir", "PySide6/qml/QtQuick/Dialogs/qmldir",
            "PySide6/qml/QtQml/objects-Debug/x.cpp.obj", "PySide6/plugins/qmltooling/q.dll",
            "ddddocr/common.onnx", "ddddocr/common_det.onnx", "cv2/opencv_videoio_ffmpeg500_64.dll",
            "cv2/cv2.pyd", "PySide6/Qt6QuickTest.dll", "PySide6/Qt6QuickVectorImageGenerator.dll",
            "PySide6/Qt6QmlXmlListModel.dll", "PySide6/Qt6QuickNativeStyle.dll",
            "PySide6/qml/Qt5Compat/GraphicalEffects/qmldir", "PySide6/qml/QtQml/XmlListModel/qmldir",
            "PySide6/plugins/platforms/qdirect2d.dll", "PySide6/plugins/platforms/qoffscreen.dll",
            "PySide6/plugins/imageformats/qtiff.dll", "PySide6/plugins/imageformats/qwebp.dll",
            "PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll",
        ]
        for name in drop:
            self.assertTrue(is_unused(name), name)

    def test_installer_keeps_dialogs(self):
        self.assertFalse(is_unused("PySide6/qml/QtQuick/Dialogs/qmldir", keep_dialogs=True))
        self.assertFalse(is_unused("PySide6/Qt6QuickDialogs2.dll", keep_dialogs=True))



class InstallerPayloadTestCase(unittest.TestCase):
    def test_onnxruntime_c_library_is_not_packaged(self):
        from prune import is_unused
        self.assertTrue(is_unused("onnxruntime/capi/onnxruntime.dll"))
        self.assertFalse(is_unused("onnxruntime/capi/onnxruntime_pybind11_state.pyd"))
        self.assertFalse(is_unused("onnxruntime/capi/onnxruntime_providers_shared.dll"))

class AccountCleanupTestCase(unittest.TestCase):
    def test_clear_account_data_keeps_other_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "config.ini").write_text(
                "[common]\nusername = 13800000000\npassword = secret\nuse_cookies = true\nspeed = 1.5\n"
                "[tiku]\nprovider = TikuYanxi\n", encoding="utf-8")
            (folder / "cookies.txt").write_text("a=b", encoding="utf-8")
            (folder / "chaoxing.log").write_text("log", encoding="utf-8")

            winsetup.clear_account_data(folder)

            config = configparser.ConfigParser(interpolation=None)
            config.read(folder / "config.ini", encoding="utf-8")
            self.assertEqual(config["common"]["username"], "")
            self.assertEqual(config["common"]["password"], "")
            self.assertEqual(config["common"]["use_cookies"], "false")
            self.assertEqual(config["common"]["speed"], "1.5")
            self.assertEqual(config["tiku"]["provider"], "TikuYanxi")
            self.assertFalse((folder / "cookies.txt").exists())
            self.assertTrue((folder / "chaoxing.log").exists())

    def test_clear_account_data_without_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            winsetup.clear_account_data(Path(tmp))  # must not raise

    def test_log_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name in ("chaoxing.log", "chaoxing.2026-11-03_10-00-00.log", "gui.log", "config.ini"):
                (folder / name).write_text("x", encoding="utf-8")
            names = sorted(p.name for p in winsetup.log_files(folder))
            self.assertEqual(names, ["chaoxing.2026-11-03_10-00-00.log", "chaoxing.log", "gui.log"])


if __name__ == "__main__":
    unittest.main()
