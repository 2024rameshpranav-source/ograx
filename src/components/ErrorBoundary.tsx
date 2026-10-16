import { Component, type ErrorInfo, type ReactNode } from "react"

type Props = { children: ReactNode }
type State = { error: Error | null }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("AquaSignal render failure", error, info)
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <main className="center">
        <section className="success">
          <span>!</span>
          <h1>AquaSignal could not render this view</h1>
          <p>
            Reload the application. If the problem continues, check the browser
            console and configured environment services.
          </p>
          <button className="primary" onClick={() => window.location.reload()}>
            Reload application
          </button>
        </section>
      </main>
    )
  }
}
