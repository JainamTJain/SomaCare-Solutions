import { Link } from "react-router-dom";
import { CareFooter } from "../components/SiteChrome.jsx";

export default function HomePage() {
  return (
    <article className="home">
      <h1>The night, kept as a stick figure</h1>
      <p className="lede">SomaCare watches how someone is lying, then tells the caregiver who to turn next. A nurse still sets every limit.</p>
      <section className="card technology">
        <h2>Technology</h2>
        <p>The camera keeps a stick figure. Rules decide the interval, the next position, and the order of the round. Nothing is sent to a language model.</p>
        <p><Link className="text-link" to="/try">See it in the app</Link></p>
      </section>
      <CareFooter />
    </article>
  );
}
