"""Adapt WiX heat harvested files to a per-user MSI with valid HKCU key paths.

Windows Installer's ICE38 requires an HKCU registry key path for all
components residing under LocalAppDataFolder. The generated registry names
are derived from WiX Component Ids and are unique across the payload.
"""
from __future__ import annotations

from pathlib import Path
import sys
import xml.etree.ElementTree as ET

NS = "http://schemas.microsoft.com/wix/2006/wi"
ET.register_namespace("", NS)
component_tag = f"{{{NS}}}Component"
file_tag = f"{{{NS}}}File"
registry_tag = f"{{{NS}}}RegistryValue"


def convert(source: Path) -> int:
    tree = ET.parse(source)
    count = 0
    for component in tree.iter(component_tag):
        files = component.findall(file_tag)
        if not files:
            continue
        for file in files:
            file.attrib.pop("KeyPath", None)
        component.append(ET.Element(registry_tag, {
            "Root": "HKCU",
            "Key": r"Software\Aurora\AutoFillMSI\Files",
            "Name": component.attrib["Id"],
            "Value": "1",
            "Type": "integer",
            "KeyPath": "yes",
        }))
        count += 1
    if not count:
        raise ValueError("Nenhum componente encontrado no XML do WiX.")
    tree.write(source, encoding="utf-8", xml_declaration=True)
    print(f"Componentes MSI por usuario atualizados: {count}")
    return count


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: fix_msi_components.py ApplicationFiles.wxs")
    convert(Path(sys.argv[1]))
