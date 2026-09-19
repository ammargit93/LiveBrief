import { useEffect, useRef, useState, type ReactNode } from "react"
import {AlertTriangle, CheckCircle2, FileText, GitCompare, Loader2, Plus, UploadCloud, X} from "lucide-react"
import { useIsMutating, useMutation } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {Link} from "react-router-dom"
const API_BASE = "http://localhost:8000"

const ACCEPTED = ".md,.pdf,.docx"
const ACCEPTED_RE = /\.(md|pdf|docx)$/i

const TABS = [
  { id: "brief", label: "Brief", icon: FileText },
  { id: "conflicts", label: "Conflicts", icon: GitCompare },
] as const

type TabId = (typeof TABS)[number]["id"]

async function uploadDocument(file: File) {
  const body = new FormData()
  const userId = localStorage.getItem("user_id")
  body.append("file", file)
  body.append("user_id", userId ?? "")
  const response = await fetch(`${API_BASE}/documents`, {
    method: "POST",
    body,
  })
  if (!response.ok) {
    let message = `Request failed: ${response.status}`
    try {
      const data = await response.json()
      if (typeof data.detail === "string") {
        message = data.detail
      }
    } catch {
      // Response wasn't JSON
    }
    throw new Error(message)
  }
  return file.name
}
function StatusStrip({
  uploadingCount,
  error,
  uploaded,
  onDismiss,
}: {
  uploadingCount: number
  error?: string
  uploaded?: string
  onDismiss: () => void
}) {
  let content: ReactNode = null

  if (uploadingCount > 0) {
    content = (
      <Row
        tone="live"
        icon={<Loader2 className="size-3.5 animate-spin" />}
      >
        Uploading {uploadingCount}{" "}
        {uploadingCount === 1 ? "file" : "files"}
      </Row>
    )
  } else if (error) {
    content = (
      <Row
        tone="error"
        icon={<AlertTriangle className="size-3.5" />}
        onDismiss={onDismiss}
      >
        Upload failed. {error}
      </Row>
    )
  } else if (uploaded) {
    content = (
      <Row
        tone="ok"
        icon={<CheckCircle2 className="size-3.5" />}
        onDismiss={onDismiss}
      >
        Uploaded <span className="font-medium">{uploaded}</span>
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

function Row({tone, icon, onDismiss, children}: {
  tone: "live" | "ok" | "error"
  icon: ReactNode
  onDismiss?: () => void
  children: ReactNode
}) {
  const style = {
    live: "bg-background text-muted-foreground",
    ok: "bg-emerald-500/5 text-emerald-700 dark:text-emerald-400 border-emerald-500/20",
    error: "border-destructive/20 bg-destructive/5 text-destructive",
  }[tone]

  return (
    <div className={`border-b ${style}`}>
      <div className="flex h-10 items-center gap-2.5 px-4 text-xs sm:px-6">
        <span className="shrink-0">{icon}</span>

        <span className="min-w-0 flex-1 truncate">
          {children}
        </span>

        {onDismiss && (
          <Button
            size="icon"
            variant="ghost"
            className="size-7 shrink-0"
            onClick={onDismiss}
            aria-label="Dismiss"
          >
            <X className="size-3" />
          </Button>
        )}
      </div>
    </div>
  )
}

function EmptyState({icon: Icon, title, body, onUpload}: {
  icon: typeof FileText
  title: string
  body: string
  onUpload: () => void
}) {
  return (
    <div className="flex min-h-[420px] flex-col items-center justify-center px-6 text-center">
      <div className="mb-4 flex size-11 items-center justify-center rounded-full border bg-muted/40">
        <Icon
          className="size-5 text-muted-foreground"
          strokeWidth={1.5}
        />
      </div>

      <h3 className="text-sm font-medium">{title}</h3>

      <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-muted-foreground">
        {body}
      </p>

      <Button size="sm" variant="outline" className="mt-5 gap-2" onClick={onUpload}>
        <UploadCloud className="size-4" />
        Upload a document
      </Button>

      <p className="mt-3 text-xs text-muted-foreground/70">
        or drop files anywhere on this page
      </p>
    </div>
  )
}

export default function Home() {
  const inputRef = useRef<HTMLInputElement>(null)
  const dragDepth = useRef(0)

  const [tab, setTab] = useState<TabId>("brief")
  const [dragging, setDragging] = useState(false)

  const upload = useMutation({
    mutationKey: ["upload"],
    mutationFn: uploadDocument,
  })

  const uploadingCount = useIsMutating({
    mutationKey: ["upload"],
  })

  const { mutate: uploadFile } = upload

  const pick = () => inputRef.current?.click()

  useEffect(() => {
    const hasFiles = (e: DragEvent) =>
      !!e.dataTransfer?.types.includes("Files")

    const onEnter = (e: DragEvent) => {
      if (!hasFiles(e)) return

      dragDepth.current++
      setDragging(true)
    }

    const onLeave = (e: DragEvent) => {
      if (!hasFiles(e)) return

      dragDepth.current = Math.max(
        0,
        dragDepth.current - 1
      )

      if (!dragDepth.current) {
        setDragging(false)
      }
    }

    const onOver = (e: DragEvent) => {
      if (hasFiles(e)) {
        e.preventDefault()
      }
    }

    const onDrop = (e: DragEvent) => {
      if (!hasFiles(e)) return

      e.preventDefault()

      dragDepth.current = 0
      setDragging(false)

      Array.from(e.dataTransfer?.files ?? [])
        .filter((file) => ACCEPTED_RE.test(file.name))
        .forEach((file) => uploadFile(file))
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
          Array.from(event.target.files ?? []).forEach((file) =>
            uploadFile(file)
          )

          event.currentTarget.value = ""
        }}
      />

      {/* Drop overlay */}
      <div
        aria-hidden={!dragging}
        className={`fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm transition-opacity duration-200 ${
          dragging
            ? "opacity-100"
            : "pointer-events-none opacity-0"
        }`}
      >
        <div
          className={`flex flex-col items-center rounded-2xl border-2 border-dashed border-foreground/30 px-16 py-14 text-center transition-transform duration-200 ${
            dragging ? "scale-100" : "scale-95"
          }`}
        >
          <UploadCloud
            className="mb-3 size-8"
            strokeWidth={1.5}
          />

          <p className="text-sm font-medium">
            Drop to add to this project
          </p>

          <p className="mt-1 text-xs text-muted-foreground">
            Markdown, PDF, or Word files
          </p>
        </div>
      </div>

      {/* Header */}

        <header className="sticky top-0 z-30 border-b bg-background/80 backdrop-blur-md">
        <div className="flex h-14 items-center justify-between px-4 sm:px-6">
            {/* Logo */}
            <Link to="/" className="flex items-center gap-2.5">
            <div className="flex size-7 items-center justify-center rounded-md bg-foreground text-xs font-bold text-background">
                L
            </div>

            <span className="text-sm font-semibold tracking-tight">
                LiveBrief
            </span>
            </Link>

            {/* Navigation */}
            <div className="flex items-center gap-2">
            <Link
                to="/login"
                className="px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
                Log in
            </Link>

            <Link
                to="/signup"
                className="rounded-md bg-foreground px-3 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
            >
                Sign up
            </Link>

            <Button
                size="sm"
                className="ml-1 gap-2"
                disabled={uploadingCount > 0}
                onClick={pick}
            >
                {uploadingCount > 0 ? (
                <Loader2 className="size-4 animate-spin" />
                ) : (
                <Plus className="size-4" />
                )}

                {uploadingCount > 0 ? "Uploading" : "Add document"}
            </Button>
            </div>
        </div>
        </header>



      <StatusStrip
        uploadingCount={uploadingCount}
        error={
          upload.isError
            ? upload.error.message
            : undefined
        }
        uploaded={
          upload.isSuccess
            ? upload.data
            : undefined
        }
        onDismiss={upload.reset}
      />

      {/* Main */}
      <main className="px-4 py-8 sm:px-6">
        <div className="mb-6">
          <h1 className="text-xl font-semibold tracking-tight">
            Project workspace
          </h1>

          <p className="mt-1 text-sm text-muted-foreground">
            Review your project documents and resolve conflicts
            between them.
          </p>
        </div>

        <Tabs
          value={tab}
          onValueChange={(value) =>
            setTab(value as TabId)
          }
          className="w-full"
        >
          <TabsList className="h-auto w-full justify-start gap-6 rounded-none border-b bg-transparent p-0">
            {TABS.map(({ id, label, icon: Icon }) => (
              <TabsTrigger
                key={id}
                value={id}
                className="-mb-px gap-2 rounded-none border-b-2 border-transparent bg-transparent px-0.5 pb-3 pt-2 text-muted-foreground shadow-none transition-colors hover:text-foreground data-[state=active]:border-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none"
              >
                <Icon
                  className="size-4"
                  strokeWidth={1.75}
                />
                {label}
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