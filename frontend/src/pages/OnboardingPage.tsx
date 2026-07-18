import { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  Dices, FileText, Globe, Lock } from "lucide-react";
import { ApiError } from "../api/client";
import { randomRepoIconId, REPO_ICONS } from "../lib/repoIcons";
import { useCreateProject } from "../api/queries";
import { useAuth } from "../auth/AuthContext";

const README_SECTIONS = [
  "Overview",
  "I/O Map",
  "Network",
  "Commissioning Notes",
  "Open Issues",
];

function slugify(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

// Only the project name is persisted today (POST /projects {name}); the
// description, visibility, and documentation controls are UI for now and aren't
// stored until the backend supports them.
export function OnboardingPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const username = user?.username ?? "username";

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<"private" | "public">("private");
  // "random" = the surprise-me default: a concrete icon is drawn on submit.
  const [icon, setIcon] = useState<string>("random");
  const [readme, setReadme] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const createProjectMut = useCreateProject();

  const slug = useMemo(() => slugify(name), [name]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);
    setSubmitting(true);
    try {
      const project = await createProjectMut.mutateAsync({
        name: name.trim(),
        icon: icon === "random" ? randomRepoIconId() : icon,
      });
      navigate("/done", {
        replace: true,
        state: { projectId: project.id, projectName: project.name },
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="onboard" onSubmit={onSubmit}>
      <div className="onboard-body">
        <h2>Create a Project</h2>
        <p className="onboard-lede">
          A project is a collection of one or more PLC files
        </p>

        {error && <div className="form-error">{error}</div>}

        {/* Project name */}
        <div className="field">
          <label className="label" htmlFor="project-name">
            Project name
          </label>
          <div className="field-hint">Use the name your team uses on the floor</div>
          <input
            id="project-name"
            className="input"
            placeholder="packaging-line-3"
            value={name}
            onChange={(e) => setName(e.target.value.replace(/ /g, "-"))}
            autoFocus
            required
          />
          <div className="url-preview">
            <span className="url-label">Project URL</span>
            <span className="url-value">
              app.spykeautomation.com/{username}/{slug || "project-name"}
            </span>
          </div>
        </div>

        {/* Description */}
        <div className="field">
          <label className="label" htmlFor="description">
            Description
          </label>
          <div className="field-hint">
            Add context for teammates and future troubleshooting
          </div>
          <textarea
            id="description"
            className="textarea tall"
            placeholder="Conveyor logic, reject station, safety interlocks, and HMI notes."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        {/* Icon */}
        <div className="field">
          <label className="label">Icon</label>
          <div className="field-hint">
            How this project shows up in lists — pick one, or let us surprise
            you
          </div>
          <div className="icon-pick">
            <button
              type="button"
              className={`icon-swatch icon-swatch-random${icon === "random" ? " selected" : ""}`}
              onClick={() => setIcon("random")}
              title="Surprise me"
            >
              <Dices size={20} strokeWidth={1.8} />
            </button>
            {REPO_ICONS.map((def) => (
              <button
                key={def.id}
                type="button"
                className={`icon-swatch tone-${def.tone}${icon === def.id ? " selected" : ""}`}
                onClick={() => setIcon(def.id)}
                title={def.label}
              >
                {def.glyph(20)}
              </button>
            ))}
          </div>
        </div>

        {/* Visibility */}
        <div className="field">
          <label className="label">Visibility</label>
          <div className="vis-cards">
            <button
              type="button"
              className={`vis-card${visibility === "private" ? " selected" : ""}`}
              onClick={() => setVisibility("private")}
            >
              <span className={`vis-radio${visibility === "private" ? " on" : ""}`} />
              <span className="vis-card-main">
                <span className="vis-card-title">
                  <Lock size={14} strokeWidth={1.8} /> Private
                </span>
                <span className="vis-card-sub">
                  Only you and the people you allow can view this project.
                </span>
              </span>
            </button>
            <button
              type="button"
              className={`vis-card${visibility === "public" ? " selected" : ""}`}
              onClick={() => setVisibility("public")}
            >
              <span className={`vis-radio${visibility === "public" ? " on" : ""}`} />
              <span className="vis-card-main">
                <span className="vis-card-title">
                  <Globe size={14} strokeWidth={1.8} /> Public
                </span>
                <span className="vis-card-sub">
                  Anyone on Spyke can view this project.
                </span>
              </span>
            </button>
          </div>
        </div>

        {/* Add project documentation */}
        <div className="field" style={{ marginBottom: 0 }}>
          <div className="setting-row">
            <div style={{ flex: 1 }}>
              <div className="setting-title">Add project documentation</div>
              <div className="setting-sub">
                Create a README with sections for I/O, network map, commissioning
                notes, and open issues.
              </div>
            </div>
            <button
              type="button"
              className={`toggle${readme ? " on" : ""}`}
              onClick={() => setReadme((v) => !v)}
              aria-pressed={readme}
              aria-label="Add project documentation"
            >
              <span className="toggle-knob" />
            </button>
          </div>
          {readme && (
            <div className="readme-preview">
              <div className="readme-preview-head">
                <FileText size={15} strokeWidth={1.8} />
                README will include these sections
              </div>
              <div className="chips">
                {README_SECTIONS.map((s) => (
                  <span className="chip" key={s}>
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="onboard-footer">
        <div className="onboard-foot-inner">
          <button
            type="button"
            className="btn-quiet"
            onClick={() => navigate("/organization", { replace: true })}
            disabled={submitting}
          >
            Skip for now
          </button>
          <div className="foot-right">
            <button
              type="button"
              className="btn-quiet"
              onClick={() => navigate(-1)}
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary btn-sm"
              disabled={!name.trim() || submitting}
            >
              {submitting ? "Creating…" : "Create project"}
            </button>
          </div>
        </div>
      </div>
    </form>
  );
}
