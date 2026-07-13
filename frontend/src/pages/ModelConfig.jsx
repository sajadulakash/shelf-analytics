import { useState } from "react";
import { Card, PageHeader, Button, Field, Select, Spinner } from "../components/primitives";

export default function ModelConfig() {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  function save() {
    setSaving(true);
    setSaved(false);
    setTimeout(() => {
      setSaving(false);
      setSaved(true);
    }, 1100);
  }

  return (
    <>
      <PageHeader
        kicker="Configuration"
        title="Model Configuration"
        subtitle="Choose the models the pipeline runs."
      />

      <Card className="p-7">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Detection · YOLO">
            <Select defaultValue="best.pt">
              <option>best.pt</option>
              <option>best_v2.pt</option>
              <option>yolo26m_sahi.pt</option>
            </Select>
          </Field>

          <Field label="Classification · SwinV2">
            <Select defaultValue="swinv2_model">
              <option>swinv2_model</option>
              <option>swinv2_v2</option>
              <option>swinv2_54cls</option>
            </Select>
          </Field>

          <Field label="Detection mode">
            <Select defaultValue="With SAHI (sliced)">
              <option>With SAHI (sliced)</option>
              <option>Without SAHI (full frame)</option>
            </Select>
          </Field>
        </div>

        <div className="mt-7 flex items-center gap-3">
          <Button onClick={save} disabled={saving}>
            {saving && <Spinner />}
            {saving ? "Saving…" : "Save configuration"}
          </Button>
          {saved && !saving && (
            <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-brand">
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Saved
            </span>
          )}
        </div>

        <p className="mono mt-6 text-xs text-muted">Preview only — simulated, no backend yet.</p>
      </Card>
    </>
  );
}
