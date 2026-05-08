import { useEffect } from 'react'
import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Strategies from './pages/Strategies'
import Backtest from './pages/Backtest'
import { wsClient } from './lib/ws'

export default function App() {
  useEffect(() => {
    wsClient.connect()
  }, [])

  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="strategies" element={<Strategies />} />
        <Route path="backtest" element={<Backtest />} />
      </Route>
    </Routes>
  )
}
