"""Compile the STA bridge; test native clipboard token and Word API contracts.

No Word instance/account is opened. Synthetic object-model tests are explicitly
not presented as an end-to-end test with the installed Microsoft Office.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CONTRACT = r'''
public sealed class WordDocStub {
    public string Text, Body;
    public int Caret, Pastes, Format, Selected;
    public bool ThrowAfterPaste;
    public WordDocStub(string text, string body) { Text=text; Body=body; Caret=text.Length; }
}
public sealed class WordRangeStub {
    public WordDocStub Doc;
    public int Start { get; set; }
    public int End { get; set; }
    public WordRangeStub(WordDocStub doc, int start, int end) { Doc=doc; Start=start; End=end; }
    public string Text { get { return Doc.Text.Substring(Start, End-Start); } }
    public WordRangeStub Duplicate { get { return new WordRangeStub(Doc,Start,End); } }
    public void SetRange(int start, int end) { Start=start; End=end; }
    public void PasteAndFormat(int format) {
        Doc.Pastes++; Doc.Format=format;
        string value=Doc.Body.Replace("\n","\r")+"\r";
        Doc.Text=Doc.Text.Substring(0,Start)+value+Doc.Text.Substring(End);
        End=Start+value.Length; Doc.Caret=End;
        if (Doc.ThrowAfterPaste) throw new InvalidOperationException("synthetic uncertain mutation");
    }
    public void Collapse(int direction) { if(direction!=0) throw new Exception(); Start=End; }
    public void Select() { Doc.Caret=End; Doc.Selected++; }
}
public sealed class WordSelectionStub {
    public WordDocStub Doc;
    public WordSelectionStub(WordDocStub doc) { Doc=doc; }
    public WordRangeStub Range { get { return new WordRangeStub(Doc,Doc.Caret,Doc.Caret); } }
}
public sealed class WordWindowStub {
    public WordSelectionStub Selection { get; set; }
    public WordWindowStub(WordDocStub doc) { Selection=new WordSelectionStub(doc); }
}
public static class AuroraWordContract {
    [DllImport("user32.dll")] private static extern bool OpenClipboard(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern bool CloseClipboard();
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] private static extern uint RegisterClipboardFormat(string name);
    [DllImport("user32.dll")] private static extern IntPtr GetClipboardData(uint fmt);
    [DllImport("kernel32.dll")] private static extern IntPtr GlobalLock(IntPtr data);
    [DllImport("kernel32.dll")] private static extern bool GlobalUnlock(IntPtr data);
    [DllImport("kernel32.dll")] private static extern UIntPtr GlobalSize(IntPtr data);
    private static string ReadFormat(string name) {
        Check(OpenClipboard(IntPtr.Zero));
        try {
            var data=GetClipboardData(RegisterClipboardFormat(name));Check(data!=IntPtr.Zero);
            var p=GlobalLock(data);Check(p!=IntPtr.Zero);
            try { var b=new byte[(int)GlobalSize(data).ToUInt64()];Marshal.Copy(p,b,0,b.Length);return Encoding.UTF8.GetString(b); }
            finally { GlobalUnlock(data); }
        } finally { CloseClipboard(); }
    }
    private static string Status(object result) {
        return (string)result.GetType().GetProperty("status").GetValue(result,null);
    }
    private static void Check(bool value) { if(!value) throw new Exception("Word contract failed"); }
    public static string Run(string token) {
        Check(AuroraWordWorker.OwnsClipboard(token));
        Check(!AuroraWordWorker.OwnsClipboard(new String('f',32)));
        string rtf=ReadFormat("Rich Text Format"),html=ReadFormat("HTML Format");
        Check(rtf.Contains("\\red255\\green0\\blue0") && rtf.Contains("\\red0\\green255\\blue0"));
        Check(rtf.Contains("\\highlight") && rtf.Contains("\\fs28") && rtf.Contains("Arial"));
        Check(html.Contains("color:#ff0000") && html.Contains("background-color:#00ff00"));
        var req=new AuroraWordWorker.Request {shortcut="/word",text="Colorida 😀\nSegunda",cursor_prefix="Colorida 😀\n"};
        string prefix="Earlier /word\nPrefix 😀 ";
        var doc=new WordDocStub(prefix+"/word", req.text);
        var result=AuroraWordWorker.Replace(new WordWindowStub(doc),req,()=>true);
        Check(Status(result)=="pasted" && doc.Pastes==1 && doc.Format==16);
        Check(doc.Text==prefix+req.text.Replace("\n","\r")+"\r");
        Check(doc.Caret==prefix.Length+req.cursor_prefix.Length && doc.Selected==1);
        var wrong=new WordDocStub(prefix+"other",req.text);
        Check(Status(AuroraWordWorker.Replace(new WordWindowStub(wrong),req,()=>true))=="changed");
        Check(wrong.Pastes==0);
        var focus=new WordDocStub(prefix+"/word",req.text); int calls=0;
        Check(Status(AuroraWordWorker.Replace(new WordWindowStub(focus),req,()=>++calls==1))=="changed");
        Check(focus.Pastes==0);
        var uncertain=new WordDocStub(prefix+"/word",req.text); uncertain.ThrowAfterPaste=true;
        Check(Status(AuroraWordWorker.Replace(new WordWindowStub(uncertain),req,()=>true))=="uncertain");
        Check(uncertain.Pastes==1);
        var insert=new WordDocStub("Original /word",req.text);
        var pick=new AuroraWordWorker.Request {shortcut="",text=req.text};
        Check(Status(AuroraWordWorker.Replace(new WordWindowStub(insert),pick,()=>true))=="pasted");
        Check(insert.Pastes==1 && insert.Text=="Original /word"+req.text.Replace("\n","\r")+"\r");
        return "{\"native_clipboard_token\":true,\"format_mode\":16,\"unicode_cursor\":true,\"changed_context_rejected\":true,\"uncertain_not_repeated\":true}";
    }
}
'''


def main():
    if sys.platform != 'win32':
        raise SystemExit('This smoke test requires Windows')
    os.environ['QT_QPA_PLATFORM'] = 'windows'
    from PySide6.QtCore import QByteArray
    from PySide6.QtWidgets import QApplication
    from app.clipboard_content import clone_mime, expansion_mime, materialize_clipboard
    app = QApplication([])
    clipboard = app.clipboard()
    original = clone_mime(clipboard.mimeData())
    token = '0123456789abcdef0123456789abcdef'
    child = None
    try:
        mime = expansion_mime('Synthetic Word payload', '<span style="font-family:Arial;font-size:14pt;color:#ff0000;background-color:#00ff00;font-weight:700">Synthetic Word payload</span>')
        mime.setData('application/x-qt-windows-mime;value="AURORA Expansion"', QByteArray(token.encode('ascii')))
        clipboard.setMimeData(mime)
        materialize_clipboard()
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'contracts.cs'
            source.write_text((ROOT/'app/word_worker.cs').read_text(encoding='utf-8')+'\n'+CONTRACT,
                              encoding='utf-8')
            script = r'''$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Web.Extensions
$refs=@([System.Web.Script.Serialization.JavaScriptSerializer].Assembly.Location,'System.dll')
Add-Type -TypeDefinition ([IO.File]::ReadAllText($env:AURORA_WORD_TEST_SOURCE)) -ReferencedAssemblies $refs
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::WriteLine([AuroraWordContract]::Run('0123456789abcdef0123456789abcdef'))'''
            powershell = Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
            child = subprocess.Popen([str(powershell),'-NoProfile','-NonInteractive','-STA','-Command',script],
                                     env=dict(os.environ,AURORA_WORD_TEST_SOURCE=str(source)),
                                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            # Intentionally do not pump this writer's GUI. Flushed formats
            # must be available to the independent Windows reader anyway.
            output,errors=child.communicate(timeout=30)
            assert child.returncode==0, errors.decode('utf-8',errors='replace')
            print('Word STA bridge contracts passed:',json.loads(output))
    finally:
        if child is not None and child.poll() is None:
            child.kill();child.communicate()
        clipboard.setMimeData(original)
        app.processEvents()


if __name__ == '__main__':
    main()
