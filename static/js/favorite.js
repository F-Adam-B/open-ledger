import 'whatwg-fetch'
import * as Cookies from "js-cookie"
import {API_BASE, HOST_PORT, HOST_URL} from './api'
require('dom4') /* Activate polyfill for closest() */

export const toggleFavorite = function (e) {
    e.stopPropagation()
    e.preventDefault()

    var form = e.target.parentNode
    toggleFavoriteWithForm (form);
}
export const toggleFavoriteWithForm = function (form, cb) {
    var method = 'PUT'

    const url = API_BASE + 'images/favorite/' + form.elements['identifier'].value
    const csrf = Cookies.get('csrftoken')

    // If they aren't logged in, tell them to do so. We can improve the UI here later.
    if (document.body.dataset.loggedIn != 'True') {
        alert("Please sign in to favorite this image.")
        if (cb) cb (false);
        return
    }

    if (form.dataset.isFavorite === 'True') {
        method = 'DELETE'
    }

    fetch(url, {
        method: method,
        body: JSON.stringify({}),
        credentials: "include",
        headers: {
            "X-CSRFToken": csrf,
            "Content-Type": "application/json"
        }
    })
        .then((response) => {
            var isFav = false;
            if (response.status === 204) { // We removed a favorite
                removeAsFavorite(form)
            }
            else if (response.status === 201 || response.status === 200) {  // We added a favorite
                setAsFavorite(form)
                isFav = true
            }
            if (cb) {
                cb (isFav);
            }
        })
}

export const setAsFavorite = (form) => {
  form.querySelector('button').classList.remove('secondary')
  form.querySelector('button').classList.add('success')
  form.dataset.isFavorite = 'True'
}
export const removeAsFavorite = (form) => {
  form.querySelector('button').classList.remove('success')
  form.querySelector('button').classList.add('secondary')
  form.dataset.isFavorite = 'False'

  // If it's actually in the favorites list, also animate removing it
  if (form.closest('.favorites-list')) {
    form.closest('.image-result').classList.add('animated')
    form.closest('.image-result').classList.add('zoomOut')
  }
}


document.addEventListener('DOMContentLoaded', () => {
  var results = document.querySelector('.image-results')
  let url = API_BASE + 'images/favorites'

  if (results && document.body.dataset.loggedIn === 'True') {
    // Get the list of the users' favorites if they're logged in

    fetch(url, {
      method: 'GET',
      credentials: "include",
      headers: {
        "Content-Type": "application/json"
      }
    })
    .then((response) => {
      return response.json()
    })
    .then((json) => {
      let identifiers = new Set()

      for (let fave of json) {
        identifiers.add(fave.image.identifier)
      }

      // For each result, check if the identifier is in the favorites set, and if
      // so update the color of the favorites button
      const imageResults = results.querySelectorAll('.image-result')

      for (let img of imageResults) {
        if (identifiers.has(img.dataset.identifier)) {
          let favoriteButton = img.querySelector('.favorite-button')
          favoriteButton.classList.remove('secondary')
          favoriteButton.classList.add('success')
          let form = img.querySelector('.add-to-favorite-container form')
          form.dataset.isFavorite = 'True'
        }
      }
    })
  }
})
