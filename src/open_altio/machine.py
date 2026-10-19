"""Memory facts the build records and the doctor checks.

The standard library reads them through `resource` and `sysconf`; Windows has neither, so there
they come from the Windows API through ctypes. macOS keeps counting memory a process has already
given back as resident until the system needs it, so a step's freed memory would add to the next
step's: there the peak is the process's physical footprint, read through ctypes, which leaves
that memory out, as Activity Monitor shows it.
"""

from __future__ import annotations

import ctypes
import os
import sys


class _ProcessMemoryCounters(ctypes.Structure):  # PROCESS_MEMORY_COUNTERS
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
        (name, ctypes.c_size_t)
        for name in (
            "PeakWorkingSetSize",
            "WorkingSetSize",
            "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage",
            "PagefileUsage",
            "PeakPagefileUsage",
        )
    ]


class _RusageInfo(ctypes.Structure):  # struct rusage_info_v4, <sys/resource.h>
    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16)] + [
        (name, ctypes.c_uint64)
        for name in (
            "ri_user_time",
            "ri_system_time",
            "ri_pkg_idle_wkups",
            "ri_interrupt_wkups",
            "ri_pageins",
            "ri_wired_size",
            "ri_resident_size",
            "ri_phys_footprint",
            "ri_proc_start_abstime",
            "ri_proc_exit_abstime",
            "ri_child_user_time",
            "ri_child_system_time",
            "ri_child_pkg_idle_wkups",
            "ri_child_interrupt_wkups",
            "ri_child_pageins",
            "ri_child_elapsed_abstime",
            "ri_diskio_bytesread",
            "ri_diskio_byteswritten",
            "ri_cpu_time_qos_default",
            "ri_cpu_time_qos_maintenance",
            "ri_cpu_time_qos_background",
            "ri_cpu_time_qos_utility",
            "ri_cpu_time_qos_legacy",
            "ri_cpu_time_qos_user_initiated",
            "ri_cpu_time_qos_user_interactive",
            "ri_billed_system_time",
            "ri_serviced_system_time",
            "ri_logical_writes",
            "ri_lifetime_max_phys_footprint",
            "ri_instructions",
            "ri_cycles",
            "ri_billed_energy",
            "ri_serviced_energy",
            "ri_interval_max_phys_footprint",
            "ri_runnable_time",
        )
    ]


RUSAGE_INFO_V4 = 4


class _MemoryStatus(ctypes.Structure):  # MEMORYSTATUSEX
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
        (name, ctypes.c_ulonglong)
        for name in (
            "ullTotalPhys",
            "ullAvailPhys",
            "ullTotalPageFile",
            "ullAvailPageFile",
            "ullTotalVirtual",
            "ullAvailVirtual",
            "ullAvailExtendedVirtual",
        )
    ]


def peak_rss_bytes() -> int:
    """This process's peak memory (DuckDB runs in it, so it is the build's): its peak resident
    memory, or on macOS its peak physical footprint."""
    if sys.platform == "darwin":
        info = _RusageInfo()
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.proc_pid_rusage(os.getpid(), RUSAGE_INFO_V4, ctypes.byref(info)) != 0:
            raise OSError(ctypes.get_errno(), "proc_pid_rusage failed")
        return int(info.ri_lifetime_max_phys_footprint)
    if sys.platform == "win32":
        from ctypes import wintypes

        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32, psapi = (ctypes.WinDLL(n, use_last_error=True) for n in ("kernel32", "psapi"))
        # Typed, so the process handle keeps all 64 bits: read as a C int it names no process.
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessMemoryCounters),
            wintypes.DWORD,
        )
        process = kernel32.GetCurrentProcess()
        if not psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.PeakWorkingSetSize)
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak * 1024)  # Linux reports KiB


def total_memory_bytes() -> int:
    """The machine's physical memory."""
    if sys.platform == "win32":
        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return int(status.ullTotalPhys)
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
