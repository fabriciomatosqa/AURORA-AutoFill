"""WiX heat directory/component fragments remain valid for per-user MSI."""
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
    def test_heat_components_use_hkcu_and_register_all_directories(self):
        # heat -cg creates directories and components in SEPARATE fragments.
        xml = """<?xml version="1.0" encoding="utf-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Fragment>
    <DirectoryRef Id="INSTALLFOLDER">
      <Directory Id="dirChild" Name="internal"/>
    </DirectoryRef>
  </Fragment>
  <Fragment>
    <ComponentGroup Id="AuroraApplicationFiles">
      <Component Id="cmpOne" Directory="INSTALLFOLDER" Guid="*">
        <File Id="filOne" KeyPath="yes" Source="a.exe"/>
      </Component>
      <Component Id="cmpTwo" Directory="dirChild" Guid="*">
        <File Id="filTwo" KeyPath="yes" Source="b.dll"/>
      </Component>
    </ComponentGroup>
  </Fragment>
</Wix>
"""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "ApplicationFiles.wxs"
            f.write_text(xml, encoding="utf-8")
            self.assertEqual(module.convert(f), 2)
            tree = ET.parse(f)
            components = [c for c in tree.iter(module.component_tag)
                          if c.find(module.file_tag) is not None]
            names = []
            for component in components:
                file = component.find(module.file_tag)
                self.assertNotIn("KeyPath", file.attrib)
                registry = component.find(module.registry_tag)
                self.assertEqual(registry.attrib["Root"], "HKCU")
                self.assertEqual(registry.attrib["KeyPath"], "yes")
                self.assertRegex(component.attrib["Guid"], r"^\{[0-9A-F-]{36}\}$")
                self.assertNotEqual(component.attrib["Guid"], "*")
                names.append(registry.attrib["Name"])
            self.assertEqual(names, ["cmpOne", "cmpTwo"])
            cleanup = next(c for c in tree.iter(module.component_tag)
                           if c.attrib["Id"] == "AuroraMsiCleanupDirectories")
            removed = [x.attrib["Directory"] for x in cleanup.findall(module.remove_tag)]
            self.assertEqual(removed, ["dirChild"])
            self.assertEqual(cleanup.find(module.registry_tag).attrib["Root"], "HKCU")
            groups = [g for g in tree.iter(f"{{{module.NS}}}ComponentGroup")
                      if g.attrib.get("Id") == "AuroraApplicationFiles"]
            refs = [x.attrib["Id"] for x in groups[0].findall(f"{{{module.NS}}}ComponentRef")]
            self.assertIn("AuroraMsiCleanupDirectories", refs)
            guids = [c.attrib["Guid"] for c in components]
            self.assertEqual(len(set(guids)), len(guids))
            f.write_text(xml, encoding="utf-8")
            module.convert(f)
            second = [c.attrib["Guid"] for c in ET.parse(f).iter(module.component_tag)
                      if c.find(module.file_tag) is not None]
            self.assertEqual(guids, second)


if __name__ == "__main__":
    unittest.main()
