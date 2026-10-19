"""Adapt WiX heat harvested files to a per-user MSI with valid HKCU key paths.

Windows Installer's ICE38 requires an HKCU registry key path for all
components residing under LocalAppDataFolder. The generated registry names
are derived from WiX Component Ids and are unique across the payload.
"""
from __future__ import annotations

from pathlib import Path
import sys
import uuid
import xml.etree.ElementTree as ET

NS = "http://schemas.microsoft.com/wix/2006/wi"
ET.register_namespace("", NS)
component_tag = f"{{{NS}}}Component"
file_tag = f"{{{NS}}}File"
registry_tag = f"{{{NS}}}RegistryValue"
directory_tag = f"{{{NS}}}Directory"
remove_tag = f"{{{NS}}}RemoveFolder"


def convert(source: Path) -> int:
    tree = ET.parse(source)
    count = 0
    for component in tree.iter(component_tag):
        files = component.findall(file_tag)
        if not files:
            continue
        for file in files:
            file.attrib.pop("KeyPath", None)
        # A component containing files AND a registry key path cannot have
        # Guid="*" in WiX 3 (CNDL0230). Derive a stable UUID from its
        # relative source path so MSI upgrades retain component identity.
        relative_path = files[0].attrib["Source"].replace("\\\\", "/").replace("\\", "/")
        component.attrib["Guid"] = "{" + str(uuid.uuid5(
            uuid.UUID("50c4af04-b7dc-48ee-aa55-c2e12f1c832f"),
            relative_path.casefold()
        )).upper() + "}"
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
    # WiX ICE64: EVERY folder under LocalAppDataFolder must have a
    # RemoveFile/RemoveFolder entry to allow clean MSI uninstallation.
    # Attach it to the first component beneath that directory, using a
    # stable identifier; Windows removes only empty directories.
    for directory in tree.iter(directory_tag):
        directory_id = directory.attrib.get("Id")
        component = next(directory.iter(component_tag), None)
        if directory_id and component is not None:
            component.append(ET.Element(remove_tag, {
                "Id": "remove_" + directory_id,
                "Directory": directory_id,
                "On": "uninstall",
            }))
    tree.write(source, encoding="utf-8", xml_declaration=True)
    print(f"Componentes MSI por usuario atualizados: {count}")
    return count


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: fix_msi_components.py ApplicationFiles.wxs")
    convert(Path(sys.argv[1]))
