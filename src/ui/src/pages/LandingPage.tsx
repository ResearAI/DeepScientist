import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import Hero, { type LandingDialogRequest } from '@/components/landing/Hero'

export function LandingPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const [dialogRequest, setDialogRequest] = useState<LandingDialogRequest | null>(null)

  useEffect(() => {
    const request =
      ((location.state as { landingDialog?: LandingDialogRequest | null } | null) ?? null)?.landingDialog ?? null
    if (!request) {
      return
    }
    setDialogRequest(request)
    navigate('.', { replace: true, state: null })
  }, [location.state, navigate])

  return (
    <Hero
      dialogRequest={dialogRequest}
      onDialogRequestConsumed={() => {
        setDialogRequest(null)
      }}
    />
  )
}
