import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import { applyAccent, getAccent } from './theme.js'
import './style.css'
applyAccent(getAccent())
createRoot(document.getElementById('root')).render(<App />)
