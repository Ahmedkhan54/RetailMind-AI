"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Bell,
  Check,
  CheckCircle2,
  Clock,
  ExternalLink,
  Laptop,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Square,
  Users,
  Video,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

/**
 * Time Range Filter Pills matching the reference video (00:20 - 00:22).
 */
export function TimeRangePills({
  activeRange = "90D",
  onChange,
}: {
  activeRange?: string;
  onChange?: (range: string) => void;
}) {
  const [selected, setSelected] = useState(activeRange);
  const ranges = ["7D", "30D", "90D", "1Y", "All"];

  const handleSelect = (range: string) => {
    setSelected(range);
    onChange?.(range);
  };

  return (
    <div className="flex items-center gap-1.5 bg-slate-100/80 p-1 rounded-full text-xs font-semibold text-slate-600 shadow-inner">
      {ranges.map((range) => {
        const isActive = selected === range;
        return (
          <button
            key={range}
            type="button"
            onClick={() => handleSelect(range)}
            className={cn(
              "px-3.5 py-1 rounded-full transition-all duration-200",
              isActive
                ? "bg-[#0f2b5c] text-white shadow-sm font-bold"
                : "hover:text-slate-900 hover:bg-slate-200/60"
            )}
          >
            {range}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Live Time Tracker Widget matching the reference video (00:06 - 00:08).
 * Dark navy card with animated digital clock digits, play/pause and stop controls.
 */
export function TimeTrackerWidget({ className }: { className?: string }) {
  const [seconds, setSeconds] = useState(5048); // Initial 01:24:08
  const [isRunning, setIsRunning] = useState(true);

  useEffect(() => {
    if (!isRunning) return;
    const interval = setInterval(() => {
      setSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [isRunning]);

  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  const pad = (n: number) => String(n).padStart(2, "0");

  const toggleRun = () => setIsRunning((prev) => !prev);
  const stopTimer = () => {
    setIsRunning(false);
    setSeconds(0);
  };

  return (
    <div
      className={cn(
        "bg-[#0f2b5c] text-white p-5 rounded-2xl shadow-lg flex flex-col justify-between relative overflow-hidden",
        className
      )}
    >
      <div className="flex items-center justify-between text-xs font-medium text-slate-300 mb-2">
        <span className="flex items-center gap-1.5 uppercase tracking-wider text-[11px] font-semibold text-blue-200">
          <Clock className="w-3.5 h-3.5" /> Time Tracker
        </span>
        <span
          className={cn(
            "w-2 h-2 rounded-full",
            isRunning ? "bg-emerald-400 animate-pulse" : "bg-slate-400"
          )}
        />
      </div>

      <div className="py-2">
        <div className="font-mono text-3xl sm:text-4xl font-extrabold tracking-wider text-white select-none">
          {pad(hrs)}:{pad(mins)}:{pad(secs)}
        </div>
        <p className="text-[11px] text-slate-300 mt-1">Project: Analytics Revamp</p>
      </div>

      <div className="flex items-center gap-3 mt-4 pt-2 border-t border-white/10">
        <button
          type="button"
          onClick={toggleRun}
          className="flex-1 py-1.5 px-3 rounded-full bg-white text-[#0f2b5c] font-semibold text-xs flex items-center justify-center gap-1.5 hover:bg-slate-100 active:scale-95 transition-all shadow-sm"
          title={isRunning ? "Pause timer" : "Resume timer"}
        >
          {isRunning ? (
            <>
              <Pause className="w-3.5 h-3.5 fill-current" /> Pause
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-current" /> Resume
            </>
          )}
        </button>
        <button
          type="button"
          onClick={stopTimer}
          className="w-8 h-8 rounded-full bg-red-500/90 hover:bg-red-600 text-white flex items-center justify-center active:scale-95 transition-all shadow-sm"
          title="Stop and reset"
        >
          <Square className="w-3 h-3 fill-current" />
        </button>
      </div>
    </div>
  );
}

/**
 * Interactive Meeting / Reminders Widget matching the reference video (00:05, 00:35 - 00:39).
 * "Check-in with Halcyon Labs" · "Start Meeting" transitions to "Leave Meeting - 00:03" live ticker.
 */
export function MeetingReminderWidget({ className }: { className?: string }) {
  const [inMeeting, setInMeeting] = useState(false);
  const [meetingSeconds, setMeetingSeconds] = useState(0);

  useEffect(() => {
    if (!inMeeting) {
      setMeetingSeconds(0);
      return;
    }
    const interval = setInterval(() => {
      setMeetingSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [inMeeting]);

  const pad = (n: number) => String(n).padStart(2, "0");
  const mins = Math.floor(meetingSeconds / 60);
  const secs = meetingSeconds % 60;

  return (
    <div
      className={cn(
        "bg-white border border-slate-100 p-5 rounded-2xl shadow-sm hover:shadow-md transition-shadow flex flex-col justify-between",
        className
      )}
    >
      <div>
        <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
          <span className="uppercase tracking-wider text-[11px] font-semibold text-slate-500">
            Reminders
          </span>
          <span className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full text-[10px] font-semibold">
            Today
          </span>
        </div>
        <h3 className="text-base font-bold text-slate-900 mt-2">
          Check-in with Halcyon Labs
        </h3>
        <p className="text-xs text-slate-500 mt-1">
          Time : 02.00 pm – 04.00 pm
        </p>
      </div>

      <div className="mt-5">
        {!inMeeting ? (
          <button
            type="button"
            onClick={() => setInMeeting(true)}
            className="w-full py-2.5 px-4 rounded-xl bg-[#0f2b5c] hover:bg-[#153a7a] text-white font-semibold text-xs flex items-center justify-center gap-2 active:scale-95 transition-all shadow-sm"
          >
            <Video className="w-4 h-4" /> Start Meeting
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setInMeeting(false)}
            className="w-full py-2.5 px-4 rounded-xl bg-red-600 hover:bg-red-700 text-white font-semibold text-xs flex items-center justify-center gap-2 active:scale-95 transition-all shadow-sm"
          >
            <span className="w-2 h-2 rounded-full bg-white animate-ping" />
            Leave Meeting - {pad(mins)}:{pad(secs)}
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Team Collaboration Widget matching the reference video (00:00, 00:05).
 */
export function TeamCollaborationWidget({ className }: { className?: string }) {
  const members = [
    {
      name: "Priya Raman",
      initials: "PR",
      color: "bg-emerald-100 text-emerald-800",
      tag: "Design System Tokens",
      status: "In progress",
      statusColor: "bg-amber-50 text-amber-700 border-amber-200",
    },
    {
      name: "Mateo Silva",
      initials: "MS",
      color: "bg-blue-100 text-blue-800",
      tag: "Passkey sign-in",
      status: "Review",
      statusColor: "bg-blue-50 text-blue-700 border-blue-200",
    },
    {
      name: "Hana Kobayashi",
      initials: "HK",
      color: "bg-purple-100 text-purple-800",
      tag: "Dashboard Widgets",
      status: "Done",
      statusColor: "bg-emerald-50 text-emerald-700 border-emerald-200",
    },
    {
      name: "Sofia Sato",
      initials: "SS",
      color: "bg-rose-100 text-rose-800",
      tag: "Packaging Safe Exports",
      status: "In progress",
      statusColor: "bg-amber-50 text-amber-700 border-amber-200",
    },
  ];

  return (
    <div
      className={cn(
        "bg-white border border-slate-100 p-5 rounded-2xl shadow-sm hover:shadow-md transition-shadow",
        className
      )}
    >
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-bold text-slate-900">Team Collaboration</h3>
          <p className="text-xs text-slate-500">Active contributors in this workspace</p>
        </div>
        <button
          type="button"
          className="text-xs font-semibold px-3 py-1 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 flex items-center gap-1 transition-colors"
        >
          <Plus className="w-3 h-3" /> Add Member
        </button>
      </div>

      <div className="space-y-3">
        {members.map((member) => (
          <div
            key={member.name}
            className="flex items-center justify-between text-xs p-2 rounded-xl hover:bg-slate-50/80 transition-colors"
          >
            <div className="flex items-center gap-3">
              <span
                className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs shadow-xs",
                  member.color
                )}
              >
                {member.initials}
              </span>
              <div>
                <p className="font-semibold text-slate-800">{member.name}</p>
                <p className="text-[11px] text-slate-400">{member.tag}</p>
              </div>
            </div>
            <span
              className={cn(
                "px-2.5 py-0.5 rounded-full text-[10px] font-semibold border",
                member.statusColor
              )}
            >
              {member.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Projects / Initiatives Widget matching the reference video (00:00, 00:35).
 */
export function ProjectStatusWidget({ className }: { className?: string }) {
  const projects = [
    { title: "Payments API v2", due: "Oct 8, 2026", color: "bg-blue-600" },
    { title: "Mobile Onboarding", due: "Oct 12, 2026", color: "bg-teal-500" },
    { title: "Design System Audit", due: "Oct 15, 2026", color: "bg-amber-500" },
    { title: "Search Revamp", due: "Oct 20, 2026", color: "bg-orange-500" },
    { title: "Q4 Launch Site", due: "Oct 22, 2026", color: "bg-purple-600" },
  ];

  return (
    <div
      className={cn(
        "bg-white border border-slate-100 p-5 rounded-2xl shadow-sm hover:shadow-md transition-shadow",
        className
      )}
    >
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-bold text-slate-900">Projects</h3>
          <p className="text-xs text-slate-500">Milestones & delivery track</p>
        </div>
        <button
          type="button"
          className="text-xs font-semibold px-3 py-1 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 flex items-center gap-1 transition-colors"
        >
          <Plus className="w-3 h-3" /> New
        </button>
      </div>

      <div className="space-y-3">
        {projects.map((proj) => (
          <div
            key={proj.title}
            className="flex items-center justify-between text-xs p-2 rounded-xl hover:bg-slate-50/80 transition-colors"
          >
            <div className="flex items-center gap-3">
              <span className={cn("w-3 h-3 rounded-sm", proj.color)} />
              <div>
                <p className="font-semibold text-slate-800">{proj.title}</p>
                <p className="text-[11px] text-slate-400">Due date: {proj.due}</p>
              </div>
            </div>
            <span className="text-[11px] font-medium text-slate-400">Active</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Topbar Notifications Dropdown matching reference video (00:02 - 00:05).
 * "Catch up — one tap clears the inbox"
 */
export function NotificationsDropdown() {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(3);
  const ref = useRef<HTMLDivElement>(null);

  const notifications = [
    {
      id: 1,
      user: "Mateo Silva",
      action: "moved Passkey sign-in to",
      target: "In progress",
      time: "5m ago",
      initials: "MS",
      color: "bg-emerald-100 text-emerald-800",
    },
    {
      id: 2,
      user: "Sofia Sato",
      action: "commented on",
      target: "Safari & Firefox regression pass",
      time: "32m ago",
      initials: "SS",
      color: "bg-purple-100 text-purple-800",
    },
    {
      id: 3,
      user: "Priya Raman",
      action: "shared Login screens v3 for",
      target: "review",
      time: "1h ago",
      initials: "PR",
      color: "bg-rose-100 text-rose-800",
    },
  ];

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const markAllRead = () => {
    setUnread(0);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="w-9 h-9 rounded-full bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 transition-colors relative"
        aria-label="Open notifications"
        aria-expanded={open}
      >
        <Bell className="w-4 h-4" />
        {unread > 0 && (
          <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-rose-500 rounded-full ring-2 ring-white" />
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-white rounded-2xl shadow-2xl border border-slate-100 z-50 p-4 animate-in fade-in zoom-in-95 duration-150">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <h4 className="text-sm font-bold text-slate-900">Notifications</h4>
              <p className="text-[11px] text-slate-400">Team activity and updates</p>
            </div>
            {unread > 0 && (
              <button
                type="button"
                onClick={markAllRead}
                className="text-xs font-semibold text-blue-600 hover:text-blue-800 hover:underline"
              >
                Mark all read
              </button>
            )}
          </div>

          <div className="divide-y divide-slate-50 mt-2 max-h-72 overflow-y-auto">
            {notifications.map((item) => (
              <div key={item.id} className="py-2.5 flex items-start gap-3 text-xs hover:bg-slate-50 rounded-xl px-2 transition-colors">
                <span
                  className={cn(
                    "w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs shrink-0",
                    item.color
                  )}
                >
                  {item.initials}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-slate-800 leading-tight">
                    <strong className="font-semibold">{item.user}</strong> {item.action}{" "}
                    <span className="font-medium text-slate-900">{item.target}</span>
                  </p>
                  <span className="text-[10px] text-slate-400 mt-0.5 block">{item.time}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-3 pt-2 border-t border-slate-100 text-center">
            <span className="text-[11px] text-slate-400 font-medium">
              Catch up — one tap clears the inbox
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Global Keyboard Shortcuts Bar & Listener matching the video:
 * "Keyboard first — G then T" (Tasks), "G then D" (Dashboard), Esc to dismiss.
 */
export function KeyboardShortcutsListener() {
  const router = useRouter();
  const [hint, setHint] = useState<string | null>(null);
  const keySequence = useRef<string[]>([]);
  const timer = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    function handleKeyDown(e: globalThis.KeyboardEvent) {
      // Don't capture when typing in inputs/textareas
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      ) {
        return;
      }

      if (e.key === "Escape") {
        setHint(null);
        return;
      }

      keySequence.current.push(e.key.toLowerCase());
      if (timer.current) clearTimeout(timer.current);

      const seq = keySequence.current.join("");

      if (seq === "gd") {
        setHint("Navigating: Dashboard (G then D)");
        router.push("/overview");
        keySequence.current = [];
        setTimeout(() => setHint(null), 1800);
        return;
      }

      if (seq === "gt") {
        setHint("Navigating: Tasks (G then T)");
        router.push("/tasks");
        keySequence.current = [];
        setTimeout(() => setHint(null), 1800);
        return;
      }

      if (seq === "ga") {
        setHint("Navigating: Visual Analytics (G then A)");
        router.push("/visual-analytics");
        keySequence.current = [];
        setTimeout(() => setHint(null), 1800);
        return;
      }

      if (seq === "gh") {
        setHint("Navigating: Help Center (G then H)");
        router.push("/help");
        keySequence.current = [];
        setTimeout(() => setHint(null), 1800);
        return;
      }

      // Reset sequence after 1 second if incomplete
      timer.current = setTimeout(() => {
        keySequence.current = [];
      }, 1000);
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [router]);

  if (!hint) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-[#0f2b5c] text-white px-5 py-2.5 rounded-full shadow-2xl text-xs font-semibold flex items-center gap-2 animate-in fade-in slide-in-from-bottom-3 duration-200 border border-white/20">
      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
      {hint}
    </div>
  );
}
