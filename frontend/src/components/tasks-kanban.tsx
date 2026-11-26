"use client";

import { useState, type DragEvent } from "react";
import {
  Calendar,
  CheckCircle2,
  Clock,
  Filter,
  GripVertical,
  Plus,
  Tag,
  User,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type TaskItem = {
  id: string;
  title: string;
  tag: string;
  tagColor: string;
  priority: "High" | "Medium" | "Low";
  priorityColor: string;
  assignee: string;
  dueDate: string;
  stage: "todo" | "in_progress" | "in_review" | "done";
};

const INITIAL_TASKS: TaskItem[] = [
  {
    id: "task-1",
    title: "Ship invoices v2",
    tag: "Frontend",
    tagColor: "bg-emerald-50 text-emerald-700 border-emerald-200",
    priority: "High",
    priorityColor: "bg-rose-50 text-rose-700 border-rose-200",
    assignee: "Noah Castell",
    dueDate: "Oct 24, 2026",
    stage: "todo",
  },
  {
    id: "task-2",
    title: "Saved filters for projects",
    tag: "Backend",
    tagColor: "bg-blue-50 text-blue-700 border-blue-200",
    priority: "Medium",
    priorityColor: "bg-amber-50 text-amber-700 border-amber-200",
    assignee: "Mateo Silva",
    dueDate: "Oct 26, 2026",
    stage: "todo",
  },
  {
    id: "task-3",
    title: "Write API endpoint docs",
    tag: "Docs",
    tagColor: "bg-purple-50 text-purple-700 border-purple-200",
    priority: "Low",
    priorityColor: "bg-slate-50 text-slate-600 border-slate-200",
    assignee: "Noah Castell",
    dueDate: "Oct 28, 2026",
    stage: "todo",
  },
  {
    id: "task-4",
    title: "Cut LCP under 2 seconds",
    tag: "Performance",
    tagColor: "bg-indigo-50 text-indigo-700 border-indigo-200",
    priority: "High",
    priorityColor: "bg-rose-50 text-rose-700 border-rose-200",
    assignee: "Sofia Sato",
    dueDate: "Oct 21, 2026",
    stage: "todo",
  },
  {
    id: "task-5",
    title: "Design login & sign-up screens",
    tag: "Design",
    tagColor: "bg-rose-50 text-rose-700 border-rose-200",
    priority: "Medium",
    priorityColor: "bg-amber-50 text-amber-700 border-amber-200",
    assignee: "Priya Raman",
    dueDate: "Oct 19, 2026",
    stage: "in_progress",
  },
  {
    id: "task-6",
    title: "Passkey sign-in",
    tag: "Security",
    tagColor: "bg-cyan-50 text-cyan-700 border-cyan-200",
    priority: "High",
    priorityColor: "bg-rose-50 text-rose-700 border-rose-200",
    assignee: "Mateo Silva",
    dueDate: "Oct 20, 2026",
    stage: "in_progress",
  },
  {
    id: "task-7",
    title: "Marketing site refresh",
    tag: "Marketing",
    tagColor: "bg-amber-50 text-amber-700 border-amber-200",
    priority: "Low",
    priorityColor: "bg-slate-50 text-slate-600 border-slate-200",
    assignee: "Hana Kobayashi",
    dueDate: "Oct 30, 2026",
    stage: "in_progress",
  },
  {
    id: "task-8",
    title: "Safari & Firefox regression pass",
    tag: "QA",
    tagColor: "bg-purple-50 text-purple-700 border-purple-200",
    priority: "Medium",
    priorityColor: "bg-amber-50 text-amber-700 border-amber-200",
    assignee: "Sofia Sato",
    dueDate: "Oct 18, 2026",
    stage: "in_review",
  },
  {
    id: "task-9",
    title: "Brand illustration set",
    tag: "Design",
    tagColor: "bg-rose-50 text-rose-700 border-rose-200",
    priority: "Low",
    priorityColor: "bg-slate-50 text-slate-600 border-slate-200",
    assignee: "Priya Raman",
    dueDate: "Oct 25, 2026",
    stage: "in_review",
  },
  {
    id: "task-10",
    title: "Homepage cleanup",
    tag: "Frontend",
    tagColor: "bg-emerald-50 text-emerald-700 border-emerald-200",
    priority: "Low",
    priorityColor: "bg-slate-50 text-slate-600 border-slate-200",
    assignee: "Noah Castell",
    dueDate: "Oct 14, 2026",
    stage: "done",
  },
  {
    id: "task-11",
    title: "Dashboard analytics widgets",
    tag: "Analytics",
    tagColor: "bg-blue-50 text-blue-700 border-blue-200",
    priority: "High",
    priorityColor: "bg-rose-50 text-rose-700 border-rose-200",
    assignee: "Noah Castell",
    dueDate: "Oct 15, 2026",
    stage: "done",
  },
];

const COLUMNS = [
  { key: "todo", label: "To do", dotColor: "bg-slate-400" },
  { key: "in_progress", label: "In progress", dotColor: "bg-blue-500" },
  { key: "in_review", label: "In review", dotColor: "bg-amber-500" },
  { key: "done", label: "Done", dotColor: "bg-emerald-500" },
] as const;

export function TasksKanbanPage() {
  const [tasks, setTasks] = useState<TaskItem[]>(INITIAL_TASKS);
  const [filter, setFilter] = useState<"all" | "my" | "high" | "week">("all");
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);

  // Form states for new task
  const [newTitle, setNewTitle] = useState("");
  const [newTag, setNewTag] = useState("Frontend");
  const [newPriority, setNewPriority] = useState<"High" | "Medium" | "Low">("Medium");
  const [newAssignee, setNewAssignee] = useState("Noah Castell");
  const [newDueDate, setNewDueDate] = useState("Oct 28, 2026");

  const filteredTasks = tasks.filter((t) => {
    if (filter === "my") return t.assignee === "Noah Castell";
    if (filter === "high") return t.priority === "High";
    if (filter === "week") return t.dueDate.includes("2026");
    return true;
  });

  const handleDragStart = (e: DragEvent<HTMLDivElement>, id: string) => {
    e.dataTransfer.setData("text/plain", id);
    setDraggingId(id);
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>, stage: TaskItem["stage"]) => {
    e.preventDefault();
    const id = e.dataTransfer.getData("text/plain") || draggingId;
    if (!id) return;
    setTasks((prev) =>
      prev.map((item) => (item.id === id ? { ...item, stage } : item))
    );
    setDraggingId(null);
  };

  const handleCreateTask = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;

    const tagColors: Record<string, string> = {
      Frontend: "bg-emerald-50 text-emerald-700 border-emerald-200",
      Backend: "bg-blue-50 text-blue-700 border-blue-200",
      Design: "bg-rose-50 text-rose-700 border-rose-200",
      Security: "bg-cyan-50 text-cyan-700 border-cyan-200",
      Performance: "bg-indigo-50 text-indigo-700 border-indigo-200",
      QA: "bg-purple-50 text-purple-700 border-purple-200",
    };

    const priColors = {
      High: "bg-rose-50 text-rose-700 border-rose-200",
      Medium: "bg-amber-50 text-amber-700 border-amber-200",
      Low: "bg-slate-50 text-slate-600 border-slate-200",
    };

    const newTask: TaskItem = {
      id: `task-${Date.now()}`,
      title: newTitle.trim(),
      tag: newTag,
      tagColor: tagColors[newTag] || tagColors.Frontend,
      priority: newPriority,
      priorityColor: priColors[newPriority],
      assignee: newAssignee,
      dueDate: newDueDate,
      stage: "todo",
    };

    setTasks((prev) => [newTask, ...prev]);
    setNewTitle("");
    setShowModal(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">Tasks</h1>
            <Badge variant="outline" className="text-xs">
              {tasks.length} tasks
            </Badge>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Drag a card to another stage, or use its menu to move it.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Filter Pills */}
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-full text-xs font-medium text-slate-600">
            <button
              type="button"
              onClick={() => setFilter("all")}
              className={cn(
                "px-3 py-1 rounded-full transition-colors",
                filter === "all" ? "bg-white text-slate-900 shadow-xs font-semibold" : "hover:text-slate-900"
              )}
            >
              All
            </button>
            <button
              type="button"
              onClick={() => setFilter("my")}
              className={cn(
                "px-3 py-1 rounded-full transition-colors",
                filter === "my" ? "bg-white text-slate-900 shadow-xs font-semibold" : "hover:text-slate-900"
              )}
            >
              My tasks
            </button>
            <button
              type="button"
              onClick={() => setFilter("high")}
              className={cn(
                "px-3 py-1 rounded-full transition-colors",
                filter === "high" ? "bg-white text-slate-900 shadow-xs font-semibold" : "hover:text-slate-900"
              )}
            >
              High priority
            </button>
            <button
              type="button"
              onClick={() => setFilter("week")}
              className={cn(
                "px-3 py-1 rounded-full transition-colors",
                filter === "week" ? "bg-white text-slate-900 shadow-xs font-semibold" : "hover:text-slate-900"
              )}
            >
              Due this week
            </button>
          </div>

          <Button
            onClick={() => setShowModal(true)}
            className="bg-[#0f2b5c] hover:bg-[#153a7a] text-white rounded-full text-xs font-semibold px-4 h-8 flex items-center gap-1.5 shadow-sm"
          >
            <Plus className="w-3.5 h-3.5" /> New Task
          </Button>
        </div>
      </div>

      {/* Kanban Board */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {COLUMNS.map((col) => {
          const colTasks = filteredTasks.filter((t) => t.stage === col.key);
          return (
            <div
              key={col.key}
              onDragOver={handleDragOver}
              onDrop={(e) => handleDrop(e, col.key)}
              className="bg-slate-50/70 border border-slate-200/70 rounded-2xl p-3 flex flex-col min-h-[500px]"
            >
              {/* Column Header */}
              <div className="flex items-center justify-between px-2 py-1.5 mb-2">
                <div className="flex items-center gap-2">
                  <span className={cn("w-2 h-2 rounded-full", col.dotColor)} />
                  <span className="text-xs font-bold text-slate-800">{col.label}</span>
                </div>
                <span className="text-[11px] font-semibold text-slate-400 bg-white px-2 py-0.5 rounded-full border border-slate-100">
                  {colTasks.length}
                </span>
              </div>

              {/* Cards List */}
              <div className="space-y-2.5 flex-1 overflow-y-auto">
                {colTasks.map((task) => (
                  <div
                    key={task.id}
                    draggable
                    onDragStart={(e) => handleDragStart(e, task.id)}
                    className={cn(
                      "bg-white border border-slate-100 p-3.5 rounded-xl shadow-xs hover:shadow-md transition-all cursor-grab active:cursor-grabbing group",
                      draggingId === task.id && "opacity-40"
                    )}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full border", task.tagColor)}>
                        {task.tag}
                      </span>
                      <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full border", task.priorityColor)}>
                        {task.priority}
                      </span>
                    </div>

                    <h4 className="text-xs font-bold text-slate-800 leading-snug group-hover:text-blue-600 transition-colors">
                      {task.title}
                    </h4>

                    <div className="flex items-center justify-between mt-3 pt-2 border-t border-slate-50 text-[11px] text-slate-400">
                      <span className="flex items-center gap-1">
                        <User className="w-3 h-3 text-slate-400" />
                        {task.assignee}
                      </span>
                      <span className="flex items-center gap-1 font-medium">
                        <Calendar className="w-3 h-3 text-slate-400" />
                        {task.dueDate}
                      </span>
                    </div>
                  </div>
                ))}

                {colTasks.length === 0 && (
                  <div className="h-28 border-2 border-dashed border-slate-200 rounded-xl flex items-center justify-center text-xs text-slate-400">
                    Drop a task here
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* New Task Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl shadow-2xl border border-slate-100 w-full max-w-md p-6 relative">
            <button
              type="button"
              onClick={() => setShowModal(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-600"
            >
              <X className="w-4 h-4" />
            </button>

            <h3 className="text-base font-bold text-slate-900 mb-1">New task</h3>
            <p className="text-xs text-slate-500 mb-4">Add a new item to your delivery pipeline</p>

            <form onSubmit={handleCreateTask} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-semibold mb-1">Task title</label>
                <input
                  type="text"
                  required
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="e.g. Ship invoices v2"
                  className="w-full px-3 py-2 border border-slate-200 rounded-xl text-xs focus:outline-hidden focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">Tag</label>
                  <select
                    value={newTag}
                    onChange={(e) => setNewTag(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-xl text-xs bg-white focus:outline-hidden focus:ring-2 focus:ring-blue-500"
                  >
                    <option>Frontend</option>
                    <option>Backend</option>
                    <option>Design</option>
                    <option>Security</option>
                    <option>Performance</option>
                    <option>QA</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">Priority</label>
                  <select
                    value={newPriority}
                    onChange={(e) => setNewPriority(e.target.value as "High" | "Medium" | "Low")}
                    className="w-full px-3 py-2 border border-slate-200 rounded-xl text-xs bg-white focus:outline-hidden focus:ring-2 focus:ring-blue-500"
                  >
                    <option>High</option>
                    <option>Medium</option>
                    <option>Low</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">Assignee</label>
                  <input
                    type="text"
                    value={newAssignee}
                    onChange={(e) => setNewAssignee(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-xl text-xs focus:outline-hidden focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">Due date</label>
                  <input
                    type="text"
                    value={newDueDate}
                    onChange={(e) => setNewDueDate(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-xl text-xs focus:outline-hidden focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-100">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setShowModal(false)}
                  className="rounded-xl text-xs"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  className="bg-[#0f2b5c] hover:bg-[#153a7a] text-white rounded-xl text-xs font-semibold px-4"
                >
                  Create task
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
