import { useEffect, useRef, useState, type ReactNode } from "react"
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient, } from "@tanstack/react-query"
import { BrowserRouter, Route, Routes, useLocation, useNavigate, } from "react-router-dom"
import { AlertTriangle, FileText, FolderOpen, GitCompare, ListChecks, Loader2, Plus, UploadCloud, X, } from "lucide-react" 
import { Badge } from "@/components/ui/badge" 
import { Button } from "@/components/ui/button" 
import { Card } from "@/components/ui/card" 
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, } from "@/components/ui/sheet"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

const API_BASE = "http://localhost:8000"
const RUNS_KEY = "livebrief.runIds"
const ACCEPTED = ".md,.pdf,.docx"
const ACCEPTED_RE = /\.(md|pdf|docx)$/i

const ACTIVE = ["queued", "processing", "running"]
const SUCCEEDED = ["done", "completed", "succeeded"]

type DocumentItem = {
  id: string
  filename: string
  status: string
  uploaded_at: string
}

type Job = {
  status: string
  current_node?: string
  error?: string | null
  filename?: string
}

type Run = { runId: string; job: Job }

const queryClient = new QueryClient()

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)

  if (!response.ok) {
    throw new Error(
      (await response.text()) || `Request failed: ${response.status}`,
    )
  }

  if (response.status === 204) return undefined as T
  return response.json()
}

function readRuns(): string[] {
  try {
    return JSON.parse(sessionStorage.getItem(RUNS_KEY) || "[]")
  } catch {
    return []
  }
}

function writeRuns(ids: string[]) {
  sessionStorage.setItem(RUNS_KEY, JSON.stringify(ids))
}

function timeAgo(iso: string) {
  const seconds = (Date.parse(iso) - Date.now()) / 1000
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" })
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ]

  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) {
      return rtf.format(Math.round(seconds / size), unit)
    }
  }
  return "just now"
}

function useDocuments() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: () => api<DocumentItem[]>("/documents"),
  })
}

function useRuns() {
  const client = useQueryClient()

  return useQuery({
    queryKey: ["jobs"],
    queryFn: async (): Promise<Run[]> => {
      const ids = readRuns()

      const settled = await Promise.allSettled(
        ids.map(async (runId) => ({
          runId,
          job: await api<Job>(`/jobs/${runId}`),
        })),
      )

      const runs = settled.flatMap((r) =>
        r.status === "fulfilled" ? [r.value] : [],
      )

      // Drop finished runs from the session and refresh the document list.
      const finished = runs.filter(({ job }) => SUCCEEDED.includes(job.status))
      if (finished.length) {
        const done = new Set(finished.map((r) => r.runId))
        writeRuns(readRuns().filter((id) => !done.has(id)))
        client.invalidateQueries({ queryKey: ["documents"] })
      }

      return runs.filter(({ job }) => !SUCCEEDED.includes(job.status))
    },
    // Only poll while there is something to watch.
    refetchInterval: () => (readRuns().length ? 3000 : false),
  })
}

function StatusStrip({ uploadError }: { uploadError?: string }) {
  const client = useQueryClient()
  const { data: runs = [] } = useRuns()

  const active = runs.filter(({ job }) => ACTIVE.includes(job.status))
  const failed = runs.find(({ job }) => job.status === "failed")

  const dismiss = (runId: string) => {
    writeRuns(readRuns().filter((id) => id !== runId))
    client.invalidateQueries({ queryKey: ["jobs"] })
  }

  let content: ReactNode = null

  if (uploadError) {
    content = (
      <Row tone="error" icon={<AlertTriangle className="size-3.5" />}>
        <span className="truncate">Upload failed. {uploadError}</span>
      </Row>
    )
  } else if (failed) {
    content = (
      <Row
        tone="error"
        icon={<AlertTriangle className="size-3.5" />}
        action={
          <Button
            size="sm"
            variant="ghost"
            className="h-7 gap-1 px-2 text-xs text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={() => dismiss(failed.runId)}
          >
            <X className="size-3" />
            Dismiss
          </Button>
        }
      >
        <span className="truncate">
          <span className="font-medium">
            {failed.job.filename || "Document"}
          </span>{" "}
          failed
          {failed.job.current_node && (
            <>
              {" "}
              at{" "}
              <span className="font-mono">{failed.job.current_node}</span>
            </>
          )}
          {failed.job.error && `: ${failed.job.error}`}
        </span>
      </Row>
    )
  } else if (active.length) {
    const current = active[0]
    content = (
      <Row
        tone="live"
        icon={
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500/60" />
            <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
          </span>
        }
        action={
          active.length > 1 ? (
            <Badge variant="secondary" className="text-[10px]">
              +{active.length - 1} more
            </Badge>
          ) : undefined
        }
      >
        <span className="truncate">
          Reconciling{" "}
          <span className="font-medium text-foreground">
            {current.job.filename || "document"}
          </span>
          <span className="mx-2 text-muted-foreground/40">/</span>
          <span className="font-mono text-foreground/80">
            {current.job.current_node || current.job.status}
          </span>
        </span>
      </Row>
    )
  }

  return (
    <div
      className={`grid transition-[grid-template-rows] duration-300 ease-out ${
        content ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
      }`}
      role="status"
      aria-live="polite"
    >
      <div className="overflow-hidden">{content}</div>
    </div>
  )
}

function Row({
  tone,
  icon,
  action,
  children,
}: {
  tone: "live" | "error"
  icon: ReactNode
  action?: ReactNode
  children: ReactNode
}) {
  const isError = tone === "error"

  return (
    <div
      className={`relative border-b ${
        isError
          ? "border-destructive/20 bg-destructive/5 text-destructive"
          : "bg-background text-muted-foreground"
      }`}
    >
      <div className="mx-auto flex h-10 max-w-6xl items-center gap-2.5 px-4 text-xs sm:px-6">
        <span className="shrink-0">{icon}</span>
        <div className="min-w-0 flex-1">{children}</div>
        {action && <div className="shrink-0">{action}</div>}
      </div>

      {!isError && (
        <div className="absolute inset-x-0 bottom-0 h-px overflow-hidden">
          <div className="h-full w-1/3 animate-pulse bg-emerald-500/70" />
        </div>
      )}
    </div>
  )
}

function StatusDot({ status }: { status: string }) {
  const tone =
    status === "failed"
      ? "bg-destructive"
      : SUCCEEDED.includes(status)
        ? "bg-emerald-500"
        : "bg-amber-500 animate-pulse"

  return <span className={`size-1.5 shrink-0 rounded-full ${tone}`} />
}

function DocumentDrawer({
  open,
  onOpenChange,
  documents,
  onPick,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  documents: DocumentItem[]
  onPick: () => void
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="flex w-[340px] flex-col gap-0 p-0 sm:max-w-[340px]">
        <SheetHeader className="border-b px-5 py-4 text-left">
          <SheetTitle className="text-sm">Documents</SheetTitle>
          <SheetDescription className="text-xs">
            {documents.length
              ? `${documents.length} in this project`
              : "Source files for this project"}
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto">
          {documents.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center px-8 text-center">
              <FolderOpen className="mb-3 size-8 text-muted-foreground/40" strokeWidth={1.5} />
              <p className="text-sm font-medium">No documents yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Add a Markdown, PDF, or Word file to start reconciling.
              </p>
            </div>
          ) : (
            <ul className="divide-y">
              {documents.map((doc) => (
                <li
                  key={doc.id}
                  className="flex items-start gap-3 px-5 py-3.5 transition-colors hover:bg-muted/50"
                >
                  <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" strokeWidth={1.5} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{doc.filename}</p>
                    <p className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                      <StatusDot status={doc.status} />
                      <span className="capitalize">{doc.status}</span>
                      <span className="text-muted-foreground/40">/</span>
                      <span>{timeAgo(doc.uploaded_at)}</span>
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="border-t p-4">
          <Button
            variant="outline"
            className="w-full gap-2"
            onClick={() => {
              onPick()
              onOpenChange(false)
            }}
          >
            <Plus className="size-4" />
            Add document
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}

const TABS = [
  { id: "brief", label: "Brief", icon: FileText },
  { id: "conflicts", label: "Conflicts", icon: GitCompare },
  { id: "reviews", label: "Review queue", icon: ListChecks },
] as const

type TabId = (typeof TABS)[number]["id"]

function EmptyState({
  icon: Icon,
  title,
  body,
  onUpload,
}: {
  icon: typeof FileText
  title: string
  body: string
  onUpload?: () => void
}) {
  return (
    <div className="flex min-h-[420px] flex-col items-center justify-center px-6 text-center">
      <div className="mb-4 flex size-11 items-center justify-center rounded-full border bg-muted/40">
        <Icon className="size-5 text-muted-foreground" strokeWidth={1.5} />
      </div>
      <h3 className="text-sm font-medium">{title}</h3>
      <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-muted-foreground">
        {body}
      </p>
      {onUpload && (
        <Button size="sm" variant="outline" className="mt-5 gap-2" onClick={onUpload}>
          <UploadCloud className="size-4" />
          Upload a document
        </Button>
      )}
      {onUpload && (
        <p className="mt-3 text-xs text-muted-foreground/70">
          or drop files anywhere on this page
        </p>
      )}
    </div>
  )
}

function AppShell() {
  const navigate = useNavigate()
  const { hash } = useLocation()
  const client = useQueryClient()

  const inputRef = useRef<HTMLInputElement>(null)
  const dragDepth = useRef(0)

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [dragging, setDragging] = useState(false)

  const tab: TabId = TABS.some((t) => t.id === hash.slice(1))
    ? (hash.slice(1) as TabId)
    : "brief"

  const setTab = (value: string) =>
    navigate({ pathname: "/", hash: value === "brief" ? "" : value }, { replace: true })

  const { data: documents = [] } = useDocuments()

  const upload = useMutation({
    mutationFn: (file: File) => {
      const body = new FormData()
      body.append("file", file)

      return api<{ document_id: string; run_id: string }>("/documents", {
        method: "POST",
        body,
      })
    },
    onSuccess: ({ run_id }) => {
      writeRuns([...new Set([...readRuns(), run_id])])
      client.invalidateQueries({ queryKey: ["documents"] })
      client.invalidateQueries({ queryKey: ["jobs"] })
    },
  })

  const pendingReviews = useQuery({
    queryKey: ["reviews"],
    queryFn: () =>
      api<{ id: string; status: string }[]>("/reviews").then((reviews) =>
        reviews.filter((review) => review.status === "pending"),
      ),
  })

  const reviewCount = pendingReviews.data?.length ?? 0
  const pick = () => inputRef.current?.click()

  // Window-wide drag and drop.
  const { mutate: uploadFile } = upload
  useEffect(() => {
    const hasFiles = (e: DragEvent) => !!e.dataTransfer?.types.includes("Files")

    const onEnter = (e: DragEvent) => {
      if (!hasFiles(e)) return
      dragDepth.current++
      setDragging(true)
    }
    const onLeave = (e: DragEvent) => {
      if (!hasFiles(e)) return
      dragDepth.current = Math.max(0, dragDepth.current - 1)
      if (!dragDepth.current) setDragging(false)
    }
    const onOver = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault()
    }
    const onDrop = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      dragDepth.current = 0
      setDragging(false)
      Array.from(e.dataTransfer?.files ?? [])
        .filter((f) => ACCEPTED_RE.test(f.name))
        .forEach((f) => uploadFile(f))
    }

    window.addEventListener("dragenter", onEnter)
    window.addEventListener("dragleave", onLeave)
    window.addEventListener("dragover", onOver)
    window.addEventListener("drop", onDrop)
    return () => {
      window.removeEventListener("dragenter", onEnter)
      window.removeEventListener("dragleave", onLeave)
      window.removeEventListener("dragover", onOver)
      window.removeEventListener("drop", onDrop)
    }
  }, [uploadFile])

  const panel = {
    brief: (
      <EmptyState
        icon={FileText}
        title="No brief yet"
        body="Upload a project document and LiveBrief will draft a brief you can check against your other files."
        onUpload={pick}
      />
    ),
    conflicts: (
      <EmptyState
        icon={GitCompare}
        title="No conflicts found"
        body="When two documents disagree, the conflict appears here with both sources side by side."
        onUpload={pick}
      />
    ),
    reviews:
      reviewCount > 0 ? (
        <EmptyState
          icon={ListChecks}
          title={`${reviewCount} ${reviewCount === 1 ? "item" : "items"} waiting for review`}
          body="Review details will appear here."
        />
      ) : (
        <EmptyState
          icon={ListChecks}
          title="Review queue is clear"
          body="Changes that need your approval will wait here."
        />
      ),
  }[tab]

  return (
    <div className="min-h-screen bg-muted/30 text-foreground antialiased">
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        accept={ACCEPTED}
        onChange={(event) => {
          Array.from(event.target.files ?? []).forEach((f) => upload.mutate(f))
          event.currentTarget.value = ""
        }}
      />

      <DocumentDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        documents={documents}
        onPick={pick}
      />

      {/* Drop overlay */}
      <div
        aria-hidden={!dragging}
        className={`fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm transition-opacity duration-200 ${
          dragging ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      >
        <div
          className={`flex flex-col items-center rounded-2xl border-2 border-dashed border-foreground/30 px-16 py-14 text-center transition-transform duration-200 ${
            dragging ? "scale-100" : "scale-95"
          }`}
        >
          <UploadCloud className="mb-3 size-8" strokeWidth={1.5} />
          <p className="text-sm font-medium">Drop to add to this project</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Markdown, PDF, or Word files
          </p>
        </div>
      </div>

      {/* Header */}
      <header className="sticky top-0 z-30 border-b bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-2.5">
            <div className="flex size-7 items-center justify-center rounded-md bg-foreground text-xs font-bold text-background">
              L
            </div>
            <span className="text-sm font-semibold tracking-tight">LiveBrief</span>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="gap-2 text-muted-foreground hover:text-foreground"
              onClick={() => setDrawerOpen(true)}
            >
              <FolderOpen className="size-4" />
              Documents
              {documents.length > 0 && (
                <span className="rounded-full bg-muted px-1.5 text-[11px] font-medium tabular-nums text-foreground">
                  {documents.length}
                </span>
              )}
            </Button>

            <Button size="sm" className="gap-2" disabled={upload.isPending} onClick={pick}>
              {upload.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Plus className="size-4" />
              )}
              {upload.isPending ? "Uploading" : "Add document"}
            </Button>
          </div>
        </div>
      </header>

      <StatusStrip uploadError={upload.isError ? upload.error.message : undefined} />

      {/* Main */}
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <div className="mb-6">
          <h1 className="text-xl font-semibold tracking-tight">Project workspace</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Review your project documents and resolve conflicts between them.
          </p>
        </div>

        <Tabs value={tab} onValueChange={setTab} className="w-full">
          <TabsList className="h-auto w-full justify-start gap-6 rounded-none border-b bg-transparent p-0">
            {TABS.map(({ id, label, icon: Icon }) => (
              <TabsTrigger
                key={id}
                value={id}
                className="-mb-px gap-2 rounded-none border-b-2 border-transparent bg-transparent px-0.5 pb-3 pt-2 text-muted-foreground shadow-none transition-colors hover:text-foreground data-[state=active]:border-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none"
              >
                <Icon className="size-4" strokeWidth={1.75} />
                {label}
                {id === "reviews" && reviewCount > 0 && (
                  <Badge className="min-w-5 justify-center px-1.5 text-[10px] tabular-nums">
                    {reviewCount}
                  </Badge>
                )}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <Card
          key={tab}
          className="mt-6 overflow-hidden shadow-none duration-200 animate-in fade-in-0"
        >
          {panel}
        </Card>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<AppShell />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}