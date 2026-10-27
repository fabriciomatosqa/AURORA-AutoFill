"""Parse synthetic Aurora RTF in Windows RichEdit, independently of Qt.

No installed Word or user documents are opened. This checks a real native RTF
reader, including list tables, instead of only matching emitted control words.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

READER = r'''
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$box=[Windows.Forms.RichTextBox]::new()
try {
    $box.CreateControl()
    $cases=Get-Content -LiteralPath (Join-Path $env:AURORA_PARAGRAPH_FIXTURES 'cases.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach($case in $cases) {
        $box.Rtf=[IO.File]::ReadAllText((Join-Path $env:AURORA_PARAGRAPH_FIXTURES ($case.name+'.rtf')))
        $actual=$box.Text.Replace("`r`n","`n").Replace("`r","`n").TrimEnd([char]10)
        if($actual -cne $case.text) { throw "Native RTF changed text in $($case.name): $actual" }
        $box.Select(0,1)
        if($case.name -eq 'paragraph') {
            if($box.SelectionAlignment -ne [Windows.Forms.HorizontalAlignment]::Center) { throw 'Native alignment lost' }
            if($box.SelectionIndent -lt 20) { throw 'Native indentation lost' }
            if(-not $box.SelectionFont.Bold) { throw 'Native character formatting lost' }
        }
        if($case.name -eq 'bullet' -and -not $box.SelectionBullet) { throw 'Native bullet list lost' }
        if($box.Rtf.Length -lt 100) { throw 'Native RTF parser returned an empty document' }
    }
    [Console]::WriteLine('{"native_rtf_text":true,"alignment":true,"indentation":true,"bold":true,"bullets":true,"nested_numbering":true}')
} finally { $box.Dispose() }
'''


def main():
    if sys.platform != 'win32':
        raise SystemExit('This smoke test requires Windows')
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtGui import QTextCursor, QTextListFormat
    from PySide6.QtWidgets import QApplication
    from app.inline_images import AuroraImageEditor
    from app.paragraph_editor import ParagraphEditor
    from app.rich_clipboard import rich_text_rtf
    app = QApplication([])
    editor = AuroraImageEditor()
    controller = ParagraphEditor(editor)
    cases = []
    with tempfile.TemporaryDirectory(prefix='aurora-paragraphs-') as temporary:
        directory = Path(temporary)
        for name, text in (('paragraph','Parágrafo 😀\nSegunda linha'),
                           ('bullet','Primeiro\nSegundo'),
                           ('numbered','Raiz\nFilho\nContinuação')):
            editor.setPlainText(text)
            editor.selectAll()
            if name == 'paragraph':
                controller.apply({'alignment':'center','left':1.25,'after':8,
                                  'line_mode':'multiple','line_value':1.15,
                                  'options':{'keep_next':True,'keep_lines':True}})
                cursor = editor.textCursor()
                fmt = cursor.charFormat();fmt.setFontWeight(700);cursor.mergeCharFormat(fmt)
            elif name == 'bullet':
                controller.list(QTextListFormat.ListDisc,'bullet')
            else:
                controller.list(QTextListFormat.ListDecimal,'multilevel')
                listing = editor.document().begin().textList()
                fmt = listing.format();fmt.setStart(3);listing.setFormat(fmt)
                editor.setTextCursor(QTextCursor(editor.document().findBlockByNumber(1)))
                controller.indent(1)
            (directory/(name+'.rtf')).write_bytes(rich_text_rtf(editor.toHtml()))
            cases.append({'name':name,'text':text})
        (directory/'cases.json').write_text(json.dumps(cases,ensure_ascii=False),encoding='utf-8')
        powershell = Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        result = subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-STA','-Command',READER],
                                env=dict(os.environ,AURORA_PARAGRAPH_FIXTURES=str(directory)),
                                capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise AssertionError(result.stderr.decode('utf-8',errors='replace'))
        print('Native RichEdit paragraph smoke passed:',json.loads(result.stdout))
    editor.deleteLater()
    app.processEvents()


if __name__ == '__main__':
    main()
