/**
 * Estado de la aplicación compartido entre microfrontends.
 * El dashboard lo escribe; resultados y escáner lo leen.
 */

export const store = {
  session: null,
  students: [],
  questions: [],
  selectedQuestionId: null,
  student: null,
};

export function resetStore() {
  store.session = null;
  store.students = [];
  store.questions = [];
  store.selectedQuestionId = null;
  store.student = null;
}
