;;; package --- vcs-resolve.el
;;; Commentary:
;;; 11 December 2016

;;; Code:

(defcustom vcs-resolve-exe "vcs-resolve" "vcs-resolve executable." :group 'local)

(defun vcs-resolve-buffer ()
  "Run `vcs-resolve` on current buffer."
  (interactive)
  (shell-command (concat vcs-resolve-exe " " (or (buffer-file-name) default-directory))))

(defun vcs-resolve-region ()
  "Run `vcs-resolve` on current region."
  (interactive)
  (shell-command (concat
                  vcs-resolve-exe " " (buffer-file-name)
                  ":"
                  (number-to-string (line-number-at-pos (region-beginning)))
                  ","
                  (number-to-string (- (line-number-at-pos (region-end)) 1)))))

;;; vcs-resolve.el ends here
