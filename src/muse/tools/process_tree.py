"""Own command descendants beyond their parent's lifetime; not a security sandbox."""
import os
import signal


class ProcessTree:
    def __init__(self, pid):
        self.pid, self.job = pid, None
        if os.name == "nt":
            self._assign_windows_job_and_resume()

    @staticmethod
    def launch_options():
        # Attach the suspended process to a job before it can create descendants.
        return {"creationflags": 0x00000004 | 0x08000000} if os.name == "nt" else {"start_new_session": True}

    def _assign_windows_job_and_resume(self):
        import ctypes as c
        from ctypes import wintypes as w

        class BasicLimits(c.Structure):
            _fields_ = [("process_time", c.c_longlong), ("job_time", c.c_longlong), ("flags", w.DWORD),
                        ("minimum_working_set", c.c_size_t), ("maximum_working_set", c.c_size_t),
                        ("active_processes", w.DWORD), ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]

        class IO(c.Structure):
            _fields_ = [(name, c.c_ulonglong) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

        class ExtendedLimits(c.Structure):
            _fields_ = [("basic", BasicLimits), ("io", IO), ("process_memory", c.c_size_t), ("job_memory", c.c_size_t),
                        ("peak_process_memory", c.c_size_t), ("peak_job_memory", c.c_size_t)]

        class ThreadEntry(c.Structure):
            _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("thread_id", w.DWORD), ("owner_pid", w.DWORD),
                        ("base_priority", w.LONG), ("delta_priority", w.LONG), ("flags", w.DWORD)]

        kernel = c.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([c.c_void_p, w.LPCWSTR], w.HANDLE),
            "SetInformationJobObject": ([w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
            "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
            "CloseHandle": ([w.HANDLE], w.BOOL),
            "CreateToolhelp32Snapshot": ([w.DWORD, w.DWORD], w.HANDLE),
            "Thread32First": ([w.HANDLE, c.POINTER(ThreadEntry)], w.BOOL),
            "Thread32Next": ([w.HANDLE, c.POINTER(ThreadEntry)], w.BOOL),
            "OpenThread": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            "ResumeThread": ([w.HANDLE], w.DWORD),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(kernel, name)
            function.argtypes, function.restype = arguments, result
        self.kernel = kernel
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise OSError("Could not create command process job")
        self.job = job
        try:
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)):
                raise OSError("Could not configure command process job")
            process = kernel.OpenProcess(0x0101, False, self.pid)
            if not process:
                raise OSError("Could not open suspended command process")
            try:
                if not kernel.AssignProcessToJobObject(job, process):
                    raise OSError("Could not contain command descendants; command was not started")
            finally:
                kernel.CloseHandle(process)
            snapshot = kernel.CreateToolhelp32Snapshot(4, 0)
            if snapshot == c.c_void_p(-1).value:
                raise OSError("Could not inspect suspended command thread")
            resumed = False
            try:
                entry = ThreadEntry()
                entry.size = c.sizeof(entry)
                found = kernel.Thread32First(snapshot, c.byref(entry))
                while found:
                    if entry.owner_pid == self.pid:
                        thread = kernel.OpenThread(2, False, entry.thread_id)
                        if thread:
                            try:
                                resumed |= kernel.ResumeThread(thread) != 0xFFFFFFFF
                            finally:
                                kernel.CloseHandle(thread)
                    found = kernel.Thread32Next(snapshot, c.byref(entry))
            finally:
                kernel.CloseHandle(snapshot)
            if not resumed:
                raise OSError("Could not start contained command process")
        except BaseException:
            self.close()
            raise

    def close(self):
        if os.name == "nt":
            if self.job is not None:
                self.kernel.CloseHandle(self.job)
                self.job = None
        else:
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
