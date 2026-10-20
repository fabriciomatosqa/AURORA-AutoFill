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
    # WiX heat puts directories and components in DIFFERENT fragments.
    # Components are not nested under their folders. ICE64 needs a
    # RemoveFolder entry for each harvested directory in the MSI RemoveFile
    # table. Put these in a dedicated component explicitly referenced by
    # the harvested component group. No suppression of ICE validations.
    directories = sorted({
        directory.attrib["Id"] for directory in tree.iter(directory_tag)
        if directory.attrib.get("Id")
    })
    if directories:
        group = next((item for item in tree.iter(f"{{{NS}}}ComponentGroup")
                      if item.attrib.get("Id") == "AuroraApplicationFiles"), None)
        if group is None:
            raise ValueError("Grupo de componentes WiX nao encontrado.")
        fragment = ET.SubElement(tree.getroot(), f"{{{NS}}}Fragment")
        ref = ET.SubElement(fragment, f"{{{NS}}}DirectoryRef", {"Id": "INSTALLFOLDER"})
        cleanup = ET.SubElement(ref, component_tag, {
            "Id": "AuroraMsiCleanupDirectories",
            "Guid": "{E58C83C3-CF7E-4AAA-9A8C-708E234D7292}",
        })
        for index, directory_id in enumerate(directories):
            ET.SubElement(cleanup, remove_tag, {
                "Id": f"RemoveHarvestedDir{index}",
                "Directory": directory_id,
                "On": "uninstall",
            })
        ET.SubElement(cleanup, registry_tag, {
            "Root": "HKCU",
            "Key": r"Software\Aurora\AutoFillMSI",
            "Name": "CleanupDirectories",
            "Value": "1",
            "Type": "integer",
            "KeyPath": "yes",
        })
        ET.SubElement(group, f"{{{NS}}}ComponentRef", {
            "Id": "AuroraMsiCleanupDirectories",
        })
    tree.write(source, encoding="utf-8", xml_declaration=True)
    print(f"Componentes MSI por usuario atualizados: {count}")
    return count


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: fix_msi_components.py ApplicationFiles.wxs")
    convert(Path(sys.argv[1]))
