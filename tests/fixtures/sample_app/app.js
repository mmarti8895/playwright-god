/**
 * Sample Todo application – client-side logic.
 * Demonstrates login and CRUD operations on a todo list.
 */

const API_BASE = '/api';

// ---- Auth helpers --------------------------------------------------------

async function login(email, password) {
  const response = await fetch(`${API_BASE}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw new Error('Login failed');
  }
  const { token } = await response.json();
  localStorage.setItem('auth_token', token);
  return token;
}

function logout() {
  localStorage.removeItem('auth_token');
  window.location.href = '/login';
}

function getToken() {
  return localStorage.getItem('auth_token');
}

// ---- Todo CRUD -----------------------------------------------------------

async function fetchTodos() {
  const response = await fetch(`${API_BASE}/todos`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  return response.json();
}

async function addTodo(title) {
  const response = await fetch(`${API_BASE}/todos`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify({ title, completed: false }),
  });
  return response.json();
}

async function toggleTodo(id, completed) {
  const response = await fetch(`${API_BASE}/todos/${id}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify({ completed }),
  });
  return response.json();
}

async function deleteTodo(id) {
  await fetch(`${API_BASE}/todos/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${getToken()}` },
  });
}

// ---- UI helpers ----------------------------------------------------------

function renderTodo(todo) {
  const li = document.createElement('li');
  li.dataset.id = todo.id;
  li.className = todo.completed ? 'completed' : '';
  li.innerHTML = `
    <input type="checkbox" ${todo.completed ? 'checked' : ''} aria-label="Mark complete" />
    <span>${todo.title}</span>
    <button class="delete-btn" aria-label="Delete todo">✕</button>
  `;
  li.querySelector('input').addEventListener('change', (e) => {
    toggleTodo(todo.id, e.target.checked).then(renderAll);
  });
  li.querySelector('.delete-btn').addEventListener('click', () => {
    deleteTodo(todo.id).then(renderAll);
  });
  return li;
}

async function renderAll() {
  const todos = await fetchTodos();
  const list = document.getElementById('todos');
  list.innerHTML = '';
  todos.forEach((t) => list.appendChild(renderTodo(t)));
}

// ---- Event listeners -----------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  const loginForm = document.querySelector('#login-form form');
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('email').value;
      const password = document.getElementById('password').value;
      try {
        await login(email, password);
        document.getElementById('login-form').classList.add('hidden');
        document.getElementById('todo-list').classList.remove('hidden');
        renderAll();
      } catch {
        alert('Login failed. Please check your credentials.');
      }
    });
  }

  const addForm = document.getElementById('add-todo-form');
  if (addForm) {
    addForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const input = document.getElementById('new-todo');
      const title = input.value.trim();
      if (!title) return;
      await addTodo(title);
      input.value = '';
      renderAll();
    });
  }
});
