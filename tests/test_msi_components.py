"""WiX components under LocalAppData must use HKCU registry key paths."""
from pathlib import Path
import importlib.util
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "msi_components", ROOT / "packaging/windows/fix_msi_components.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MSIComponentsTests(unittest.TestCase):
    def test_heat_components_use_hkcu_and_remove_file_keypath(self):
        xml = """<?xml version="1.0" encoding="utf-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Fragment><DirectoryRef Id="INSTALLFOLDER">
    <Component Id="cmpOne" Guid="*">
      <File Id="filOne" KeyPath="yes" Source="a.exe"/>
    </Component>
    <Component Id="cmpTwo" Guid="*">
      <File Id="filTwo" KeyPath="yes" Source="b.dll"/>
    </Component>
  </DirectoryRef></Fragment>
</Wix>
"""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "ApplicationFiles.wxs"
            f.write_text(xml, encoding="utf-8")
            self.assertEqual(module.convert(f), 2)
            tree = ET.parse(f)
            names = []
            for component in tree.iter(module.component_tag):
                file = component.find(module.file_tag)
                self.assertNotIn("KeyPath", file.attrib)
                registry = component.find(module.registry_tag)
                self.assertEqual(registry.attrib["Root"], "HKCU")
                self.assertEqual(registry.attrib["KeyPath"], "yes")
                self.assertRegex(component.attrib["Guid"], r"^\{[0-9A-F-]{36}\}$")
                self.assertNotEqual(component.attrib["Guid"], "*")
                names.append(registry.attrib["Name"])
            self.assertEqual(names, ["cmpOne", "cmpTwo"])
            guids_first = [c.attrib["Guid"] for c in tree.iter(module.component_tag)]
            self.assertEqual(len(set(guids_first)), 2)
            f.write_text(xml, encoding="utf-8")
            module.convert(f)
            guids_again = [c.attrib["Guid"] for c in ET.parse(f).iter(module.component_tag)]
            self.assertEqual(guids_first, guids_again)


if __name__ == "__main__":
    unittest.main()
