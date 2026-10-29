// Compiled UI Automation loop. Only reads text and selects validated ranges.
// No clipboard/keyboard/network access. Document data stays in anonymous pipes.
using System;
using System.IO;
using System.Text;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using System.Windows.Automation;
using System.Windows.Automation.Text;

public static class AuroraAccessibilityWorker
{
    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    private const int Limit = 65535;
    private const TextPatternRangeEndpoint Start = TextPatternRangeEndpoint.Start;
    private const TextPatternRangeEndpoint End = TextPatternRangeEndpoint.End;

    public sealed class Request
    {
        public int process { get; set; }
        public string window { get; set; }
        public string control { get; set; }
        public string action { get; set; }
        public string text { get; set; }
        public string[] identity { get; set; }
        public int selection_start { get; set; }
        public int selection_end { get; set; }
        public int start { get; set; }
        public int end { get; set; }
    }

    private sealed class State
    {
        public AutomationElement Focused;
        public TextPattern Pattern;
        public TextPatternRange Document;
        public TextPatternRange Selection;
        public string Text;
        public string[] Identity;
        public int Start;
        public int End;
    }

    private static bool SameIdentity(string[] a, string[] b)
    {
        if (a == null || b == null || a.Length != b.Length) return false;
        for (int i = 0; i < a.Length; i++) if (a[i] != b[i]) return false;
        return true;
    }

    private static string RuntimeId(AutomationElement element)
    {
        return String.Join(",", element.GetRuntimeId());
    }

    private static bool InScope(AutomationElement focused, Request request)
    {
        if (focused == null) return false;
        if (String.IsNullOrEmpty(request.window)) return focused.Current.ProcessId == request.process;
        long window, control;
        if (!Int64.TryParse(request.window, out window) ||
            !Int64.TryParse(request.control, out control) ||
            GetForegroundWindow().ToInt64() != window) return false;
        // Chromium/Teams may expose a renderer PID different from the host.
        for (int depth = 0; focused != null && depth < 40; depth++)
        {
            long handle = focused.Current.NativeWindowHandle;
            if (handle != 0 && (handle == window || handle == control)) return true;
            focused = TreeWalker.RawViewWalker.GetParent(focused);
        }
        return false;
    }

    private static bool SameRange(TextPatternRange a, TextPatternRange b)
    {
        return a.CompareEndpoints(Start, b, Start) == 0 &&
               a.CompareEndpoints(End, b, End) == 0;
    }

    private static bool StillCurrent(State state, Request request)
    {
        var focused = AutomationElement.FocusedElement;
        return InScope(focused, request) && RuntimeId(focused) == state.Identity[1] &&
               state.Document.GetText(Limit) == state.Text;
    }

    private static State Read(Request request, out string status)
    {
        status = "changed";
        var focused = AutomationElement.FocusedElement;
        if (!InScope(focused, request)) return null;
        if (focused.Current.IsPassword) { status = "unsupported"; return null; }
        string focusedId = RuntimeId(focused);
        var element = focused;
        TextPattern pattern = null;
        for (int depth = 0; element != null && depth < 8; depth++)
        {
            if (element.Current.IsPassword) { status = "unsupported"; return null; }
            object candidate;
            if (element.TryGetCurrentPattern(TextPattern.Pattern, out candidate))
            {
                pattern = (TextPattern)candidate;
                break;
            }
            element = TreeWalker.ControlViewWalker.GetParent(element);
        }
        if (pattern == null) { status = "unsupported"; return null; }
        var ranges = pattern.GetSelection();
        if (ranges.Length != 1) { status = "unsupported"; return null; }
        var selection = ranges[0];
        var document = pattern.DocumentRange;
        string text = document.GetText(Limit);
        if (text.Length >= Limit) { status = "too_large"; return null; }
        var prefix = document.Clone();
        prefix.MoveEndpointByRange(End, selection, Start);
        string beforeStart = prefix.GetText(Limit);
        bool collapsed = selection.CompareEndpoints(Start, selection, End) == 0;
        // Most requests have a caret, not a selection: avoid another large read.
        string beforeEnd = beforeStart;
        if (!collapsed)
        {
            var endPrefix = document.Clone();
            endPrefix.MoveEndpointByRange(End, selection, End);
            beforeEnd = endPrefix.GetText(Limit);
        }
        if (!text.StartsWith(beforeStart, StringComparison.Ordinal) ||
            !text.StartsWith(beforeEnd, StringComparison.Ordinal) ||
            beforeStart.Length > beforeEnd.Length ||
            selection.GetText(Limit) != text.Substring(beforeStart.Length, beforeEnd.Length - beforeStart.Length))
            return null;
        var state = new State {
            Focused = focused, Pattern = pattern, Document = document, Selection = selection,
            Text = text, Start = beforeStart.Length, End = beforeEnd.Length,
            Identity = new string[] { focused.Current.ProcessId.ToString(), focusedId, RuntimeId(element) }
        };
        var again = pattern.GetSelection();
        if (again.Length != 1 || !SameRange(selection, again[0]) || !StillCurrent(state, request)) return null;
        status = "ok";
        return state;
    }

    private static TextPatternRange Position(State state, int offset)
    {
        var range = state.Document.Clone();
        if (offset == 0) range.MoveEndpointByRange(End, state.Document, Start);
        else if (offset == state.Text.Length) range.MoveEndpointByRange(Start, state.Document, End);
        else
        {
            string prefix = state.Text.Substring(0, offset);
            range = state.Document.FindText(prefix, false, false);
            if (range == null || range.GetText(Limit) != prefix ||
                range.CompareEndpoints(Start, state.Document, Start) != 0)
                throw new InvalidOperationException();
            range.MoveEndpointByRange(Start, range, End);
        }
        return range;
    }

    private static TextPatternRange TargetRange(State state, Request request)
    {
        // Shortcut immediately before the caret: find just the suffix in the
        // prefix ending at that caret. No FindText of the entire document prefix,
        // no assumptions about UIA Character units (emoji/combining marks).
        if (state.Start == state.End && request.end == state.Start && request.start < request.end)
        {
            string shortcut = state.Text.Substring(request.start, request.end - request.start);
            var prefix = state.Document.Clone();
            prefix.MoveEndpointByRange(End, state.Selection, Start);
            var found = prefix.FindText(shortcut, true, false);
            if (found != null && found.GetText(Limit) == shortcut &&
                found.CompareEndpoints(End, state.Selection, Start) == 0) return found;
            throw new InvalidOperationException();
        }
        var begin = Position(state, request.start);
        var end = Position(state, request.end);
        begin.MoveEndpointByRange(End, end, Start);
        return begin;
    }

    private static object Snapshot(State state, Request request, int start, int end)
    {
        return new { status = "ok", text = state.Text, start = start, end = end,
                     identity = state.Identity, window = request.window, control = request.control };
    }

    private static object Caret(Request request)
    {
        // Read geometry only. Never retrieve or store the user's text.
        var focused = AutomationElement.FocusedElement;
        if (!InScope(focused, request)) return new { status = "changed" };
        if (focused.Current.IsPassword) return new { status = "unsupported" };
        TextPattern pattern = null;
        var element = focused;
        for (int depth = 0; element != null && depth < 8; depth++)
        {
            if (element.Current.IsPassword) return new { status = "unsupported" };
            object value;
            if (element.TryGetCurrentPattern(TextPattern.Pattern, out value))
            {
                pattern = (TextPattern)value;
                break;
            }
            element = TreeWalker.ControlViewWalker.GetParent(element);
        }
        if (pattern == null) return new { status = "unsupported" };
        var ranges = pattern.GetSelection();
        if (ranges.Length != 1) return new { status = "unsupported" };
        var cursor = ranges[0].Clone();
        cursor.MoveEndpointByRange(End, cursor, Start);
        System.Windows.Rect[] bounds = cursor.GetBoundingRectangles();
        bool previous = false;
        // Chromium may return no rectangles for a collapsed caret. Use the
        // nearest character only to infer geometry, not its textual content.
        if (bounds.Length == 0)
        {
            var next = cursor.Clone();
            if (next.MoveEndpointByUnit(End, TextUnit.Character, 1) > 0)
                bounds = next.GetBoundingRectangles();
        }
        if (bounds.Length == 0)
        {
            var last = cursor.Clone();
            if (last.MoveEndpointByUnit(Start, TextUnit.Character, -1) < 0)
            {
                bounds = last.GetBoundingRectangles();
                previous = true;
            }
        }
        if (bounds.Length == 0) return new { status = "unsupported" };
        // A wrapped selection may report more than one line. With the
        // collapsed/one-character range, the final usable rectangle suffices.
        var rect = bounds[bounds.Length - 1];
        if (rect.IsEmpty || rect.Height < 6 || rect.Height > 160 ||
            rect.Width > 400 || Double.IsNaN(rect.X) || Double.IsNaN(rect.Y) ||
            Math.Abs(rect.X) > 100000 || Math.Abs(rect.Y) > 100000 ||
            !InScope(AutomationElement.FocusedElement, request))
            return new { status = "unsupported" };
        return new {
            status = "caret", x = previous ? rect.Right : rect.Left,
            y = rect.Top, height = rect.Height,
            window = request.window, control = request.control
        };
    }

    public static object Handle(Request request)
    {
        if (request.action == "caret") return Caret(request);
        string status;
        var state = Read(request, out status);
        if (state == null) return new { status = status };
        if (request.action != "select") return Snapshot(state, request, state.Start, state.End);
        if (request.text != state.Text || !SameIdentity(request.identity, state.Identity) ||
            request.selection_start != state.Start || request.selection_end != state.End ||
            request.start < 0 || request.end < request.start || request.end > state.Text.Length)
            return new { status = "changed" };
        var target = TargetRange(state, request);
        if (target.GetText(Limit) != state.Text.Substring(request.start, request.end - request.start) ||
            !StillCurrent(state, request)) return new { status = "changed" };
        target.Select(); // exactly once; never resend while waiting for an editor
        var actual = state.Pattern.GetSelection();
        if (actual.Length != 1 || !StillCurrent(state, request)) return new { status = "changed" };
        if (SameRange(target, actual[0]))
            return Snapshot(state, request, request.start, request.end);
        // WebViews can acknowledge before GetSelection reflects the new range.
        // Only an unchanged old selection qualifies for a pending ACK.
        if (!SameRange(state.Selection, actual[0])) return new { status = "changed" };
        return new { status = "selection_requested", window = request.window,
                     control = request.control, identity = state.Identity };
    }

    public static void Run()
    {
        Console.InputEncoding = new UTF8Encoding(false);
        Console.OutputEncoding = new UTF8Encoding(false);
        var json = new JavaScriptSerializer { MaxJsonLength = 1048576, RecursionLimit = 16 };
        Console.WriteLine("{\"ready\":true}");
        Console.Out.Flush();
        string line;
        while ((line = Console.ReadLine()) != null && line.Length <= 1048576)
        {
            object response;
            try { response = Handle(json.Deserialize<Request>(line)); }
            catch { response = new { status = "unavailable" }; }
            Console.WriteLine(json.Serialize(response));
            Console.Out.Flush();
        }
    }
}
