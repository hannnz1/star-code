$ErrorActionPreference = 'Stop'
$processFile = Join-Path $PSScriptRoot '.muse\processes.json'
if (!(Test-Path -LiteralPath $processFile)) { Write-Output 'No managed MUSE processes.'; exit 0 }
$saved = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
foreach ($entry in $saved) {
    $running = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    if ($running -and $running.StartTime.ToUniversalTime() -eq ([datetime]$entry.started).ToUniversalTime()) {
        # Do not use taskkill or Kill(true): in a restricted token they can
        # terminate only the parent and silently leave descendants running.
        if (!('MuseOwnedProcessTree' -as [type])) {
            Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class MuseOwnedProcessTree {
    static readonly Dictionary<uint, IntPtr> rootHandles = new Dictionary<uint, IntPtr>();
    static readonly Dictionary<uint, IntPtr> preparedHandles = new Dictionary<uint, IntPtr>();
    static readonly Dictionary<uint, List<uint>> preparedChildren = new Dictionary<uint, List<uint>>();
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    struct Entry {
        public uint size, usage, pid; public UIntPtr heap;
        public uint module, threads, parent; public int priority; public uint flags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst=260)] public string executable;
    }
    [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr CreateToolhelp32Snapshot(uint flags, uint pid);
    [DllImport("kernel32.dll", EntryPoint="Process32FirstW", SetLastError=true)] static extern bool First(IntPtr snapshot, ref Entry entry);
    [DllImport("kernel32.dll", EntryPoint="Process32NextW", SetLastError=true)] static extern bool Next(IntPtr snapshot, ref Entry entry);
    [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetProcessTimes(IntPtr handle, out long created, out long exited, out long kernel, out long user);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool TerminateProcess(IntPtr handle, uint code);
    [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr handle, uint timeout);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    static List<uint> Children(uint parent) {
        IntPtr snapshot = CreateToolhelp32Snapshot(2, 0);
        if (snapshot == new IntPtr(-1)) throw new Win32Exception(Marshal.GetLastWin32Error());
        try {
            var result = new List<uint>(); var entry = new Entry(); entry.size = (uint)Marshal.SizeOf(typeof(Entry));
            if (!First(snapshot, ref entry)) throw new Win32Exception(Marshal.GetLastWin32Error());
            do { if (entry.parent == parent && entry.pid != parent) result.Add(entry.pid); } while (Next(snapshot, ref entry));
            int error = Marshal.GetLastWin32Error();
            if (error != 18) throw new Win32Exception(error);
            return result;
        } finally { CloseHandle(snapshot); }
    }
    public static void Hold(uint pid, long expectedCreation) {
        IntPtr handle = OpenProcess(0x00101001, false, pid);
        if (handle == IntPtr.Zero) {
            int error = Marshal.GetLastWin32Error();
            if (error == 87) return;
            throw new Win32Exception(error);
        }
        try {
            long created, exited, kernel, user;
            if (!GetProcessTimes(handle, out created, out exited, out kernel, out user)) throw new Win32Exception(Marshal.GetLastWin32Error());
            if (created != expectedCreation || rootHandles.ContainsKey(pid)) throw new InvalidOperationException("Process identity changed.");
            PrepareChildren(pid, created, new HashSet<uint>(), 0);
            rootHandles.Add(pid, handle);
        } catch { ClearPrepared(); CloseHandle(handle); throw; }
    }
    static void ClearPrepared() {
        foreach (IntPtr handle in preparedHandles.Values) CloseHandle(handle);
        preparedHandles.Clear(); preparedChildren.Clear();
    }
    static void PrepareChildren(uint pid, long created, HashSet<uint> visited, int depth) {
        if (depth > 64 || visited.Count > 4096 || !visited.Add(pid)) throw new InvalidOperationException("Process tree limit reached.");
        var found = Children(pid); preparedChildren.Add(pid, found);
        foreach (uint child in found) {
            IntPtr handle = OpenChild(pid, child, created);
            preparedHandles.Add(child, handle);
            long childCreated, exited, kernel, user;
            if (!GetProcessTimes(handle, out childCreated, out exited, out kernel, out user)) throw new Win32Exception(Marshal.GetLastWin32Error());
            PrepareChildren(child, childCreated, visited, depth + 1);
        }
    }
    public static void Stop(uint pid, long expectedCreation) {
        IntPtr handle;
        if (rootHandles.TryGetValue(pid, out handle)) rootHandles.Remove(pid);
        else handle = IntPtr.Zero;
        var visited = new HashSet<uint>();
        try { StopNode(pid, expectedCreation, true, visited, 0, handle); }
        finally { ClearPrepared(); }
    }
    static IntPtr OpenChild(uint parent, uint child, long earliest) {
        IntPtr handle = OpenProcess(0x00101001, false, child);
        if (handle == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
        try {
            long created, exited, kernel, user;
            if (!GetProcessTimes(handle, out created, out exited, out kernel, out user)) throw new Win32Exception(Marshal.GetLastWin32Error());
            if (created < earliest || !Children(parent).Contains(child)) throw new InvalidOperationException("Child process identity changed.");
            return handle;
        } catch { CloseHandle(handle); throw; }
    }
    static void StopNode(uint pid, long earliest, bool root, HashSet<uint> visited, int depth, IntPtr ownedHandle) {
        if (depth > 64 || visited.Count > 4096 || !visited.Add(pid)) throw new InvalidOperationException("Process tree limit reached.");
        IntPtr handle = ownedHandle != IntPtr.Zero ? ownedHandle : OpenProcess(0x00101001, false, pid);
        if (handle == IntPtr.Zero) {
            int error = Marshal.GetLastWin32Error();
            if (error == 87) return; // Already exited; a reused PID has a different creation time.
            throw new Win32Exception(error);
        }
        var heldChildren = new Dictionary<uint, IntPtr>();
        try {
            long created, exited, kernel, user;
            if (!GetProcessTimes(handle, out created, out exited, out kernel, out user)) throw new Win32Exception(Marshal.GetLastWin32Error());
            if (root ? created != earliest : created < earliest) throw new InvalidOperationException("Process identity changed.");
            // Snapshot must be available before terminating anything. Keep the
            // parent handle open so its PID cannot be reused during traversal.
            var children = Children(pid);
            List<uint> previouslyHeld;
            if (preparedChildren.TryGetValue(pid, out previouslyHeld)) {
                foreach (uint child in previouslyHeld) if (!children.Contains(child)) children.Add(child);
            }
            // Venv launchers can terminate their Python child when they exit.
            // Retain child handles FIRST, so its descendants remain traceable
            // even if that intermediate process exits with its parent.
            foreach (uint child in children) {
                IntPtr childHandle;
                if (preparedHandles.TryGetValue(child, out childHandle)) preparedHandles.Remove(child);
                else childHandle = OpenChild(pid, child, created);
                heldChildren.Add(child, childHandle);
            }
            if (WaitForSingleObject(handle, 0) != 0 && !TerminateProcess(handle, 1)) {
                int error = Marshal.GetLastWin32Error();
                // A parent launcher can already be terminating this child.
                // Its handle may not signal immediately. Keep the exact held
                // identity and await exit; never reopen by PID or ignore a
                // still-running process whose termination was denied.
                if (WaitForSingleObject(handle, 5000) != 0) throw new Win32Exception(error);
            }
            if (WaitForSingleObject(handle, 5000) != 0) throw new InvalidOperationException("Process did not exit.");
            // Capture children born between the first snapshot and termination.
            foreach (uint child in Children(pid)) if (!children.Contains(child)) children.Add(child);
            foreach (uint child in children) {
                IntPtr childHandle;
                if (heldChildren.TryGetValue(child, out childHandle)) heldChildren.Remove(child);
                else childHandle = OpenChild(pid, child, created);
                StopNode(child, created, false, visited, depth + 1, childHandle);
            }
        } finally {
            foreach (IntPtr childHandle in heldChildren.Values) CloseHandle(childHandle);
            CloseHandle(handle);
        }
    }
}
'@
        }
        [MuseOwnedProcessTree]::Hold([uint32]$entry.pid, ([datetime]$entry.started).ToUniversalTime().ToFileTimeUtc())
        [MuseOwnedProcessTree]::Stop([uint32]$entry.pid, ([datetime]$entry.started).ToUniversalTime().ToFileTimeUtc())
        Write-Output "Stopped MUSE $($entry.role)."
    }
}
Write-Output 'Task records remain on disk. Active tasks recover after their lease expires; uncertain writes require reconciliation.'
