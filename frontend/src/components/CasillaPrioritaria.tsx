/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
/** «Clase prioritaria»: se procesa antes que las demás de la cola. Se puede marcar durante la clase y mientras espera su turno. */
export function CasillaPrioritaria({ marcada, deshabilitada, onCambiar }: { marcada: boolean; deshabilitada: boolean; onCambiar: (marcada: boolean) => void }) {
  return (
    <label className="flex min-h-10 items-center gap-3 text-sm">
      <input
        type="checkbox"
        className="size-5 rounded border-input accent-primary"
        checked={marcada}
        disabled={deshabilitada}
        onChange={(e) => onCambiar(e.target.checked)}
      />
      <span>
        Clase prioritaria <span className="text-muted-foreground">(se procesa antes que las demás)</span>
      </span>
    </label>
  )
}
