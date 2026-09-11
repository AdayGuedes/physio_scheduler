# Buenas Prácticas — Physio Scheduler

## Objetivo

- Mostrar cómo se debe trabajar en este proyecto para que lo que se escriba
  y lo que se suba se mantenga seguro, legible y eficiente.

## Criterio de aceptación

Cuando se vaya a hacer una tarea hay tres tipos:

1. Aportación nueva/crear algo → `feature`/`feat`
2. Modificar algo ya creado → `refactor`
3. Arreglar un bug → `bugfix`/`fix`

En todos los nombres de rama tiene que poner eltipo/PS/nombre de la tarea.
PS viene de Physio Scheduler.

En los commits se debe de poner `feat` en vez de `feature` y `bugfix` en vez
de `fix`, ya que `fix` se podrá usar para cuando en una PR de `feature`, por
ejemplo, haya que solucionar algún error.

## Ejemplos de uso

Cuando se vaya a hacer una nueva tarea se debe de crear una rama aparte para
no subir los cambios a `main`. Dependiendo de lo que se vaya a hacer, el
nombre de la rama debe ser:

1. Feature → nombre de rama: `feature/PS-x/nombre-de-rama`
2. Refactor → nombre de rama: `refactor/PS-x/nombre-de-rama`
3. Bugfix → nombre de rama: `bugfix/PS-x/nombre-de-rama`

Para los commits:

1. Feature → `"feat: nombre del commit"`
2. Refactor → `"refactor: nombre del commit"`
3. Bugfix → `"bugfix: nombre del commit"`
4. Si en una PR de `feature` o `refactor` hay que solucionar un problema se
   usará `"fix: nombre del commit"`
