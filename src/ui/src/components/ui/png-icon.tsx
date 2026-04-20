'use client'

import * as React from 'react'
import { assetUrl } from '@/lib/assets'
import { cn } from '@/lib/utils'

type PngIconProps = {
  name: string
  alt?: string
  size?: number
  className?: string
  priority?: boolean
  fallback: React.ReactNode
}

export function PngIcon({
  name,
  alt,
  size = 16,
  className,
  priority = false,
  fallback,
}: PngIconProps) {
  const [failed, setFailed] = React.useState(false)
  const useInverted = !name.startsWith('inverted/')
  const resolvedAlt = alt ?? name

  if (failed) return <>{fallback}</>

  return (
    <>
      <img
        src={assetUrl(`icons/${name}.png`)}
        alt={resolvedAlt}
        width={size}
        height={size}
        className={cn('object-contain', useInverted && 'dark:hidden', className)}
        loading={priority ? 'eager' : 'lazy'}
        decoding="async"
        draggable={false}
        onError={() => setFailed(true)}
      />
      {useInverted ? (
        <img
          src={assetUrl(`icons/inverted/${name}.png`)}
          alt={resolvedAlt}
          width={size}
          height={size}
          className={cn('object-contain hidden dark:block', className)}
          loading={priority ? 'eager' : 'lazy'}
          decoding="async"
          draggable={false}
          onError={() => setFailed(true)}
        />
      ) : null}
    </>
  )
}

export default PngIcon
