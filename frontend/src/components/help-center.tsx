"use client";

import { useState } from "react";
import {
  BookOpen,
  ChevronDown,
  ChevronUp,
  CreditCard,
  FolderKanban,
  HelpCircle,
  Mail,
  MessageSquare,
  Search,
  Sparkles,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const TOPICS = [
  { id: "started", label: "Getting started", articles: "2 articles", icon: BookOpen },
  { id: "projects", label: "Projects & tasks", articles: "2 articles", icon: FolderKanban },
  { id: "team", label: "Team", articles: "1 articles", icon: Users },
  { id: "billing", label: "Billing & plans", articles: "3 articles", icon: CreditCard },
];

const FAQS = [
  {
    topic: "team",
    q: "How do I invite a teammate?",
    a: "Open Team from the sidebar and press Invite member. They appear immediately with a pending status until they accept their invitation link.",
  },
  {
    topic: "projects",
    q: "Who can see my time tracker?",
    a: "Time tracker entries are private to your workspace account unless logged against a shared project milestone.",
  },
  {
    topic: "started",
    q: "How do I import and map business datasets?",
    a: "Go to Data Upload, drop in any CSV or Excel file up to 25MB, and confirm or adjust the detected column mappings.",
  },
  {
    topic: "projects",
    q: "Can I customize the Overview dashboard?",
    a: "Yes! Use the Dashboard Mode toggle to switch to 'Customize' mode. You can drag and drop widgets, resize them across columns, choose different chart types, and save your layout.",
  },
  {
    topic: "billing",
    q: "What export formats are supported?",
    a: "RetailMind supports Power BI PBIP/TMDL/PBIR projects, executive PDF reports, business PDF summaries, and clean CSV/Excel downloads.",
  },
];

export function HelpCenterPage() {
  const [selectedTopic, setSelectedTopic] = useState("started");
  const [search, setSearch] = useState("");
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  const filteredFaqs = FAQS.filter((faq) => {
    const matchesSearch = !search.trim() ||
      faq.q.toLowerCase().includes(search.toLowerCase()) ||
      faq.a.toLowerCase().includes(search.toLowerCase());
    const matchesTopic = selectedTopic === "all" || faq.topic === selectedTopic || search.trim().length > 0;
    return matchesSearch && matchesTopic;
  });

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-[#0f2b5c] text-white rounded-3xl p-6 sm:p-10 shadow-xl relative overflow-hidden">
        <div className="max-w-2xl relative z-10">
          <span className="text-xs font-semibold uppercase tracking-wider text-blue-200 flex items-center gap-1.5 mb-2">
            <HelpCircle className="w-4 h-4" /> Help Center
          </span>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
            How can we help?
          </h1>
          <p className="text-xs sm:text-sm text-blue-100/90 mt-2">
            Answers, shortcuts, and guidance whenever you need one.
          </p>

          <div className="mt-6 relative max-w-lg">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search articles or questions…"
              className="w-full bg-white text-slate-800 text-xs pl-10 pr-4 py-2.5 rounded-xl shadow-inner focus:outline-hidden focus:ring-2 focus:ring-blue-400"
            />
          </div>
        </div>

        {/* Topic Pills */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-8 pt-6 border-t border-white/10 relative z-10">
          {TOPICS.map((topic) => {
            const isSelected = selectedTopic === topic.id;
            const Icon = topic.icon;
            return (
              <button
                key={topic.id}
                type="button"
                onClick={() => setSelectedTopic(topic.id)}
                className={cn(
                  "p-3 rounded-2xl text-left transition-all flex items-center gap-3",
                  isSelected
                    ? "bg-white text-[#0f2b5c] font-bold shadow-lg scale-102"
                    : "bg-white/10 text-white hover:bg-white/15"
                )}
              >
                <Icon className="w-4 h-4 shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs truncate">{topic.label}</p>
                  <p className={cn("text-[10px]", isSelected ? "text-slate-400 font-normal" : "text-blue-200")}>
                    {topic.articles}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Grid: FAQs & Shortcuts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* FAQs Accordion */}
        <div className="lg:col-span-2 bg-white border border-slate-100 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-slate-900">Frequently asked</h3>
            <button
              type="button"
              onClick={() => setOpenIndex((prev) => (prev === null ? 0 : null))}
              className="text-xs text-blue-600 hover:text-blue-800 font-medium"
            >
              {openIndex === null ? "Show first" : "Collapse"}
            </button>
          </div>

          <div className="divide-y divide-slate-100">
            {filteredFaqs.map((faq, idx) => {
              const isOpen = openIndex === idx;
              return (
                <div key={faq.q} className="py-3.5">
                  <button
                    type="button"
                    onClick={() => setOpenIndex(isOpen ? null : idx)}
                    className="w-full flex items-center justify-between text-left text-xs font-semibold text-slate-800 hover:text-blue-600 transition-colors"
                  >
                    <span>{faq.q}</span>
                    {isOpen ? (
                      <ChevronUp className="w-4 h-4 text-slate-400 shrink-0" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
                    )}
                  </button>
                  {isOpen && (
                    <p className="text-xs text-slate-500 mt-2 leading-relaxed pl-1 animate-in fade-in duration-150">
                      {faq.a}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Sidebar: Shortcuts & Support */}
        <div className="space-y-4">
          {/* Shortcuts Card */}
          <div className="bg-white border border-slate-100 rounded-2xl p-5 shadow-sm">
            <h4 className="text-xs font-bold text-slate-900 mb-3">Keyboard shortcuts</h4>
            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between text-slate-600 py-1">
                <span>Search anywhere</span>
                <kbd className="px-2 py-0.5 bg-slate-100 rounded-md font-mono text-[10px] text-slate-700 border">
                  ⌘K
                </kbd>
              </div>
              <div className="flex items-center justify-between text-slate-600 py-1">
                <span>Go to dashboard</span>
                <kbd className="px-2 py-0.5 bg-slate-100 rounded-md font-mono text-[10px] text-slate-700 border">
                  G then D
                </kbd>
              </div>
              <div className="flex items-center justify-between text-slate-600 py-1">
                <span>Go to tasks</span>
                <kbd className="px-2 py-0.5 bg-slate-100 rounded-md font-mono text-[10px] text-slate-700 border">
                  G then T
                </kbd>
              </div>
              <div className="flex items-center justify-between text-slate-600 py-1">
                <span>Go to visual analytics</span>
                <kbd className="px-2 py-0.5 bg-slate-100 rounded-md font-mono text-[10px] text-slate-700 border">
                  G then A
                </kbd>
              </div>
              <div className="flex items-center justify-between text-slate-600 py-1">
                <span>Dismiss dialog / popover</span>
                <kbd className="px-2 py-0.5 bg-slate-100 rounded-md font-mono text-[10px] text-slate-700 border">
                  Esc
                </kbd>
              </div>
            </div>
          </div>

          {/* Contact Support Card */}
          <div className="bg-slate-900 text-white rounded-2xl p-5 shadow-sm">
            <h4 className="text-xs font-bold mb-1">Still stuck?</h4>
            <p className="text-[11px] text-slate-300 mb-4">
              Our team answers under 10 minutes, Monday to Friday.
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                className="flex-1 bg-white/10 hover:bg-white/20 text-white border-white/20 text-xs h-8"
                onClick={() => alert("Live support chat initiated.")}
              >
                <MessageSquare className="w-3.5 h-3.5 mr-1.5" /> Start a chat
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="flex-1 bg-white/10 hover:bg-white/20 text-white border-white/20 text-xs h-8"
                onClick={() => window.location.href = "mailto:support@retailmind.ai"}
              >
                <Mail className="w-3.5 h-3.5 mr-1.5" /> Email us
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
