'use client'

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  variant?: 'default' | 'light'
  className?: string
}

const sizeClasses = {
  sm: 'w-4 h-4 border-2',
  md: 'w-8 h-8 border-2',
  lg: 'w-12 h-12 border-4',
}

const variantClasses = {
  default: 'border-slate-200 border-t-indigo-600',
  light: 'border-white/30 border-t-white',
}

export default function Spinner({ size = 'md', variant = 'default', className = '' }: SpinnerProps) {
  return (
    <div
      className={`rounded-full animate-spin ${sizeClasses[size]} ${variantClasses[variant]} ${className}`}
      role="status"
      aria-label="Loading"
    />
  )
}
