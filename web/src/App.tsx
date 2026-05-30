import { ChatPage } from './components/ChatPage';
import { useAuth } from './hooks/useAuth';

export default function App() {
  const auth = useAuth();

  if (auth.loading) {
    return (
      <div className="loading-screen">
        <p>加载中…</p>
      </div>
    );
  }

  return <ChatPage auth={auth} />;
}
