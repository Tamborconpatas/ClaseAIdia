/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
/**
 * Cuenta cuántas fórmulas y diagramas se están dibujando todavía. Imprimir o exportar antes de que terminen daría un
 * documento con huecos, así que `esperarDibujos` espera a que el contador llegue a cero.
 */
let pendientes = 0

/** Marca que empieza un dibujo; devuelve la función que lo marca terminado (se puede llamar más de una vez sin efecto). */
export function empezarDibujo(): () => void {
  pendientes++
  let terminado = false
  return () => {
    if (!terminado) {
      terminado = true
      pendientes--
    }
  }
}

// Con un temporizador y no con requestAnimationFrame: el navegador no llama a este último en una pestaña oculta o tapada.
const esperarUnPoco = () => new Promise<void>((r) => setTimeout(r, 50))

/** Espera a que no quede nada por dibujar (con tope, para no colgarse si algo nunca termina). */
export async function esperarDibujos(maximoMs = 20_000): Promise<void> {
  const limite = Date.now() + maximoMs
  let tranquilo = 0
  while (tranquilo < 4 && Date.now() < limite) {
    await esperarUnPoco()
    tranquilo = pendientes === 0 ? tranquilo + 1 : 0 // un rato seguido sin nada pendiente: React ya montó lo que faltaba
  }
}

/** Cuántos dibujos faltan (para los tests y para depurar). */
export const dibujosPendientes = () => pendientes
