// Word's native object model, bound to the foreground _WwG document window.
// No GetActiveObject/CreateObject: never attach to an arbitrary Word instance.
using System;
using System.IO;
using System.Text;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;

public static class AuroraWordWorker
{
    private delegate bool EnumWindow(IntPtr hwnd, IntPtr data);
    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern IntPtr GetAncestor(IntPtr hwnd, uint flag);
    [DllImport("user32.dll")] private static extern bool IsChild(IntPtr parent, IntPtr child);
    [StructLayout(LayoutKind.Sequential)] private struct GuiInfo
    {
        public uint size, flags;
        public IntPtr active, focus, capture, menu, move, caret;
        public int left, top, right, bottom;
    }
    [DllImport("user32.dll")] private static extern bool GetGUIThreadInfo(uint thread, ref GuiInfo info);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern int GetClassName(IntPtr hwnd, StringBuilder text, int size);
    [DllImport("user32.dll")] private static extern bool EnumChildWindows(IntPtr hwnd, EnumWindow callback, IntPtr data);
    [DllImport("oleacc.dll")] private static extern int AccessibleObjectFromWindow(IntPtr hwnd, uint id, ref Guid iid, [MarshalAs(UnmanagedType.Interface)] out object value);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern uint RegisterClipboardFormat(string name);
    [DllImport("user32.dll")] private static extern bool OpenClipboard(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern bool CloseClipboard();
    [DllImport("user32.dll")] private static extern IntPtr GetClipboardData(uint format);
    [DllImport("user32.dll")] private static extern uint GetClipboardSequenceNumber();
    [DllImport("kernel32.dll")] private static extern IntPtr GlobalLock(IntPtr data);
    [DllImport("kernel32.dll")] private static extern bool GlobalUnlock(IntPtr data);
    [DllImport("kernel32.dll")] private static extern UIntPtr GlobalSize(IntPtr data);

    public sealed class Request
    {
        public int process { get; set; }
        public string window { get; set; }
        public string control { get; set; }
        public string shortcut { get; set; }
        public string text { get; set; }
        public string cursor_prefix { get; set; }
        public string token { get; set; }
    }

    private static object Get(object value, string name)
    { return value.GetType().InvokeMember(name, BindingFlags.GetProperty, null, value, null); }
    private static object Call(object value, string name, params object[] args)
    { return value.GetType().InvokeMember(name, BindingFlags.InvokeMethod, null, value, args); }
    private static void Release(object value)
    { try { if (value != null && Marshal.IsComObject(value)) Marshal.ReleaseComObject(value); } catch { } }
    private static long HandleValue(object value)
    { return unchecked((uint)Convert.ToInt32(value)); }

    public static bool OwnsClipboard(string token)
    {
        if (String.IsNullOrEmpty(token) || token.Length != 32) return false;
        bool opened = false;
        for (int attempt = 0; attempt < 5 && !opened; attempt++)
        {
            opened = OpenClipboard(IntPtr.Zero);
            if (!opened) System.Threading.Thread.Sleep(10);
        }
        if (!opened) return false;
        try
        {
            var data = GetClipboardData(RegisterClipboardFormat("AURORA Expansion"));
            if (data == IntPtr.Zero) return false;
            ulong size = GlobalSize(data).ToUInt64();
            if (size < 32 || size > 64) return false;
            var pointer = GlobalLock(data);
            if (pointer == IntPtr.Zero) return false;
            try
            {
                byte[] bytes = new byte[(int)size];
                Marshal.Copy(pointer, bytes, 0, bytes.Length);
                return Encoding.ASCII.GetString(bytes).TrimEnd('\0') == token;
            }
            finally { GlobalUnlock(data); }
        }
        finally { CloseClipboard(); }
    }

    private static string Normal(string text)
    { return text.Replace("\r\n", "\n").Replace("\r", "\n"); }

    public static int PrefixOffset(string text, string prefix)
    {
        int at = 0;
        foreach (char wanted in Normal(prefix))
        {
            if (at >= text.Length) throw new InvalidOperationException();
            char actual = text[at];
            int step = actual == '\r' && at + 1 < text.Length && text[at + 1] == '\n' ? 2 : 1;
            if ((actual == '\r' ? '\n' : actual) != wanted) throw new InvalidOperationException();
            at += step;
        }
        return at;
    }

    // Public boundary permits contract tests with an owned synthetic object
    // model. The production entry point supplies the real HWND/clipboard guards.
    public static object Replace(object window, Request request, Func<bool> valid)
    {
        object selection = null, original = null, range = null, current = null;
        bool submitted = false;
        try
        {
            if (request == null || request.shortcut == null || request.shortcut.Length > 128
                || request.text == null || request.text.IndexOf('\0') >= 0 || !valid())
                return new { status = "changed" };
            selection = Get(window, "Selection");
            original = Get(selection, "Range");
            int start = Convert.ToInt32(Get(original, "Start"));
            int end = Convert.ToInt32(Get(original, "End"));
            bool inserting = request.shortcut.Length == 0;
            if (!inserting && (start != end || start < request.shortcut.Length)) return new { status = "changed" };
            range = Get(original, "Duplicate");
            if (!inserting) Call(range, "SetRange", start - request.shortcut.Length, end);
            string originalText = inserting ? Convert.ToString(Get(range, "Text")) : request.shortcut;
            if (Convert.ToString(Get(range, "Text")) != originalText) return new { status = "changed" };
            current = Get(selection, "Range");
            if (Convert.ToInt32(Get(current, "Start")) != start || Convert.ToInt32(Get(current, "End")) != end
                || !valid() || Convert.ToString(Get(range, "Text")) != originalText)
                return new { status = "changed" };
            int begin = Convert.ToInt32(Get(range, "Start"));
            submitted = true;
            Call(range, "PasteAndFormat", 16); // wdFormatOriginalFormatting, one call
            string inserted = Convert.ToString(Get(range, "Text"));
            bool confirmed = Normal(inserted) == Normal(request.text)
                || Normal(inserted) == Normal(request.text) + "\n";
            bool cursorApplied = request.cursor_prefix == null;
            if (valid())
            {
                if (request.cursor_prefix != null && confirmed)
                {
                    int position = begin + PrefixOffset(inserted, request.cursor_prefix);
                    Call(range, "SetRange", position, position);
                }
                else Call(range, "Collapse", 0); // wdCollapseEnd
                Call(range, "Select");
                cursorApplied = request.cursor_prefix == null || confirmed;
            }
            return new { status = "pasted", confirmed = confirmed,
                         cursor = cursorApplied, clipboard_sequence = GetClipboardSequenceNumber() };
        }
        catch { return new { status = submitted ? "uncertain" : "unavailable" }; }
        finally { Release(current); Release(range); Release(original); Release(selection); }
    }

    private static object Handle(Request request)
    {
        long raw, rawControl;
        if (request == null || !Int64.TryParse(request.window, out raw)
            || !Int64.TryParse(request.control, out rawControl)) return new { status = "changed" };
        IntPtr root = new IntPtr(raw);
        IntPtr control = new IntPtr(rawControl);
        if (GetForegroundWindow() != root) return new { status = "changed" };
        object native = null;
        EnumChildWindows(root, delegate(IntPtr child, IntPtr unused) {
            var name = new StringBuilder(128);
            GetClassName(child, name, name.Capacity);
            // Never use the document's old selection when typing in Find,
            // a ribbon input, or another control in the same Word window.
            if (name.ToString() != "_WwG" || (child != control && !IsChild(child, control))) return true;
            Guid iid = new Guid("00020400-0000-0000-C000-000000000046");
            return AccessibleObjectFromWindow(child, 0xfffffff0, ref iid, out native) != 0 || native == null;
        }, IntPtr.Zero);
        if (native == null) return new { status = "unavailable" };
        try
        {
            Func<bool> valid = delegate {
                var info = new GuiInfo { size = (uint)Marshal.SizeOf(typeof(GuiInfo)) };
                return GetForegroundWindow() == root
                    && GetGUIThreadInfo(0, ref info) && info.focus == control
                    && GetAncestor(new IntPtr(HandleValue(Get(native, "Hwnd"))), 2) == root
                    && OwnsClipboard(request.token);
            };
            return Replace(native, request, valid);
        }
        finally { Release(native); }
    }

    public static void Run()
    {
        Console.InputEncoding = new UTF8Encoding(false);
        Console.OutputEncoding = new UTF8Encoding(false);
        var json = new JavaScriptSerializer { MaxJsonLength = 16777216, RecursionLimit = 12 };
        Console.WriteLine("{\"ready\":true}"); Console.Out.Flush();
        string line;
        while ((line = Console.ReadLine()) != null && line.Length <= 16777216)
        {
            object response;
            try { response = Handle(json.Deserialize<Request>(line)); }
            catch { response = new { status = "unavailable" }; }
            Console.WriteLine(json.Serialize(response)); Console.Out.Flush();
        }
    }
}
